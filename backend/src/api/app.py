"""
Flash Sale Inventory Gateway REST API (FLS-106, FLS-108, FLS-116).
Provides high-throughput endpoints for reservation, checkout, and live stock monitoring.
"""

from typing import Optional, Dict, Any, List
import time
from fastapi import FastAPI, Depends, HTTPException, status, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db, AsyncSessionLocal
from observability.metrics import refresh_inventory_gauges, export_metrics_text
from observability.oversell import global_oversell_detector, OversellIncident
from stock.reservation import StockReservationService
from flow.checkout import CheckoutService
from models.inventory import InventoryRecord, InventoryManager, InventorySchema
from models.catalog import ProductManager, ProductSchema
from models.campaigns import CampaignManager, CampaignSchema, CampaignRecord
from models.orders import OrderRecord
from flow.waiting_room import WaitingRoomManager
from auth.service import (
    AuthService, SessionManager, UserLimitManager, BlockedUserRuleManager,
    AuthException, InvalidCredentialsError, UserBlockedError, AccountLockedError,
    PerUserLimitExceededError, InvalidSessionError
)
from sqlalchemy import select, func
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from contextlib import asynccontextmanager
from models.catalog import ProductRecord
from models.inventory import InventoryRecord
from db.database import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    try:
        async with AsyncSessionLocal() as session:
            c_res = await session.execute(select(func.count(InventoryRecord.sku_id)))
            count = c_res.scalar() or 0
            if count == 0:
                products = [
                    ProductRecord(product_id="prod-cyber-shoe", title="Cyber Runner 2077", original_price_cents=12000),
                    ProductRecord(product_id="prod-titan-gpu", title="RTX Titan Black Edition", original_price_cents=99900),
                    ProductRecord(product_id="prod-fold-phone", title="Quantum Fold X", original_price_cents=79900),
                    ProductRecord(product_id="prod-ultra-console", title="HyperStation Pro", original_price_cents=49900),
                    ProductRecord(product_id="prod-smart-watch", title="ChronoPulse Smart Watch", original_price_cents=19900),
                ]
                session.add_all(products)
                records = [
                    InventoryRecord(sku_id="sku-shoe-cyber-01", product_id="prod-cyber-shoe", total_allocated=50, available=32, reserved=8, sold=10),
                    InventoryRecord(sku_id="sku-gpu-titan-99", product_id="prod-titan-gpu", total_allocated=20, available=4, reserved=6, sold=10),
                    InventoryRecord(sku_id="sku-phone-fold-x", product_id="prod-fold-phone", total_allocated=100, available=85, reserved=5, sold=10),
                    InventoryRecord(sku_id="sku-console-ultra", product_id="prod-ultra-console", total_allocated=30, available=0, reserved=2, sold=28),
                    InventoryRecord(sku_id="sku-watch-smart-v2", product_id="prod-smart-watch", total_allocated=75, available=60, reserved=5, sold=10),
                ]
                session.add_all(records)
                await session.commit()
    except Exception as e:
        print(f"Warning: Demo inventory seed skipped: {e}")
    yield

app = FastAPI(
    title="Flash Sale Inventory Gateway",
    version="1.0.0",
    description="Atomic inventory reservation and checkout gateway",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------- Request / Response Models -----------------

class ReservationRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1)
    quantity: int = Field(default=1, gt=0)
    lease_seconds: int = Field(default=300, gt=0)

class CheckoutRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    sku_id: str = Field(..., min_length=1)
    quantity: int = Field(default=1, gt=0)
    unit_price_cents: int = Field(..., ge=0)
    reservation_token: str = Field(..., min_length=1)
    idempotency_key: str = Field(..., min_length=1)
    max_quantity_per_user: Optional[int] = None

# ----------------- Endpoints -----------------

@app.get("/healthz")
async def healthz():
    uptime = time.time() - START_TIME
    return {"status": "ok", "service": "flash-sale-gateway", "uptime_seconds": round(uptime, 2)}

@app.post("/api/v1/reservations", status_code=status.HTTP_200_OK)
async def create_reservation(
    req: ReservationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Atomic Stock Reservation API (FLS-106).
    """
    service = StockReservationService(db)
    ok, msg, data = await service.reserve_stock(
        sku_id=req.sku_id,
        user_id=req.user_id,
        quantity=req.quantity,
        lease_seconds=req.lease_seconds
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=msg
        )
    return {"success": True, "message": msg, "reservation": data}

@app.get("/api/v1/stock/{sku_id}")
async def get_stock(
    sku_id: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Real-time stock query endpoint.
    """
    service = StockReservationService(db)
    st = await service.get_stock_status(sku_id)
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU '{sku_id}' not found")
    return st

@app.post("/api/v1/checkout", status_code=status.HTTP_200_OK)
async def process_checkout(
    req: CheckoutRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Atomic Checkout API (FLS-108).
    """
    service = CheckoutService(db)
    ok, msg, data = await service.process_checkout(
        user_id=req.user_id,
        sku_id=req.sku_id,
        quantity=req.quantity,
        unit_price_cents=req.unit_price_cents,
        reservation_token=req.reservation_token,
        idempotency_key=req.idempotency_key,
        max_quantity_per_user=req.max_quantity_per_user
    )
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=msg
        )
    return {"success": True, "message": msg, "order": data}

@app.get("/api/v1/dashboard/stock")
async def get_all_stock(db: AsyncSession = Depends(get_db)):
    """
    Live stock dashboard feed for operations console (FLS-116).
    """
    stmt = select(InventoryRecord)
    res = await db.execute(stmt)
    records = res.scalars().all()
    return [
        {
            "sku_id": r.sku_id,
            "product_id": r.product_id,
            "total_allocated": r.total_allocated,
            "available": r.available,
            "reserved": r.reserved,
            "sold": r.sold,
            "in_stock": r.available > 0,
            "sell_through_percentage": round((r.sold / r.total_allocated * 100.0), 1) if r.total_allocated > 0 else 0.0
        }
        for r in records
    ]

@app.get("/api/v1/dashboard/orders")
async def get_dashboard_orders(db: AsyncSession = Depends(get_db)):
    """
    Real-time order monitoring feed (FLS-123).
    """
    stmt = select(OrderRecord).order_by(OrderRecord.created_at.desc()).limit(50)
    res = await db.execute(stmt)
    records = res.scalars().all()
    return [
        {
            "order_id": o.order_id,
            "user_id": o.user_id,
            "sku_id": o.sku_id,
            "quantity": o.quantity,
            "total_amount_cents": o.total_amount_cents,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None
        }
        for o in records
    ]

@app.get("/api/v1/dashboard/summary")
async def get_dashboard_summary(db: AsyncSession = Depends(get_db)):
    """
    Flash-sale dashboard aggregate summary (FLS-115).
    """
    inv_stmt = select(InventoryRecord)
    inv_res = await db.execute(inv_stmt)
    inv_records = inv_res.scalars().all()

    total_allocated = sum(r.total_allocated for r in inv_records)
    total_available = sum(r.available for r in inv_records)
    total_reserved = sum(r.reserved for r in inv_records)
    total_sold = sum(r.sold for r in inv_records)

    order_stmt = select(func.count(OrderRecord.order_id))
    total_orders = (await db.scalar(order_stmt)) or 0

    camp_stmt = select(func.count(CampaignRecord.campaign_id))
    total_campaigns = (await db.scalar(camp_stmt)) or 0

    sell_through = round((total_sold / total_allocated * 100.0), 1) if total_allocated > 0 else 0.0

    return {
        "status": "OPERATIONAL",
        "total_campaigns": total_campaigns,
        "total_allocated": total_allocated,
        "total_available": total_available,
        "total_reserved": total_reserved,
        "total_sold": total_sold,
        "total_orders": total_orders,
        "sell_through_percentage": sell_through
    }

@app.get("/api/v1/dashboard/counters")
async def get_dashboard_counters(db: AsyncSession = Depends(get_db)):
    """
    Real-time operational counters (FLS-125).
    """
    inv_stmt = select(InventoryRecord)
    inv_res = await db.execute(inv_stmt)
    inv_records = inv_res.scalars().all()

    total_allocated = sum(r.total_allocated for r in inv_records)
    total_available = sum(r.available for r in inv_records)
    total_reserved = sum(r.reserved for r in inv_records)
    total_sold = sum(r.sold for r in inv_records)

    order_stmt = select(func.count(OrderRecord.order_id))
    total_orders = (await db.scalar(order_stmt)) or 0

    gmv_stmt = select(func.sum(OrderRecord.total_amount_cents))
    total_gmv_cents = (await db.scalar(gmv_stmt)) or 0

    sell_through = round((total_sold / total_allocated * 100.0), 1) if total_allocated > 0 else 0.0

    return {
        "total_allocated": total_allocated,
        "total_available": total_available,
        "total_reserved": total_reserved,
        "total_sold": total_sold,
        "total_orders": total_orders,
        "total_gmv_cents": total_gmv_cents,
        "sell_through_percentage": sell_through,
        "waiting_room_active": len(global_waiting_room._queues)
    }


@app.get("/api/v1/dashboard/alerts")
async def get_dashboard_alerts(threshold_pct: float = 20.0, db: AsyncSession = Depends(get_db)):
    """
    Low-stock alerts monitor (FLS-126).
    """
    stmt = select(InventoryRecord)
    res = await db.execute(stmt)
    records = res.scalars().all()

    alerts = []
    for r in records:
        if r.total_allocated > 0:
            remaining_pct = (r.available / r.total_allocated) * 100.0
            if remaining_pct <= threshold_pct or r.available <= 5:
                alerts.append({
                    "sku_id": r.sku_id,
                    "product_id": r.product_id,
                    "available": r.available,
                    "total_allocated": r.total_allocated,
                    "remaining_pct": round(remaining_pct, 1),
                    "alert_level": "CRITICAL" if r.available == 0 else "WARNING",
                    "message": f"SKU '{r.sku_id}' is at low stock ({r.available}/{r.total_allocated} available, {remaining_pct:.1f}%)"
                })

    return alerts

class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=6)

class LoginRequest(BaseModel):
    identifier: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

security_bearer = HTTPBearer(auto_error=False)

@app.post("/api/v1/auth/register", status_code=status.HTTP_201_CREATED)
async def register_user(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    User registration endpoint (FLS-026).
    """
    auth = AuthService(db)
    try:
        user = await auth.register(req.username, req.email, req.password)
        return {
            "success": True,
            "user_id": user.id,
            "username": user.username,
            "email": user.email,
            "status": user.status.value
        }
    except AuthException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

@app.post("/api/v1/auth/login", status_code=status.HTTP_200_OK)
async def login_user(
    req: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    User authentication endpoint (FLS-026).
    Handles lockout with exponential cool-down (FLS-037) and blocked status (FLS-036).
    """
    auth = AuthService(db)
    try:
        user, sess = await auth.authenticate(req.identifier, req.password)
        return {
            "success": True,
            "session_token": sess.session_token,
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "status": user.status.value
            },
            "expires_at": sess.expires_at.isoformat()
        }
    except UserBlockedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=e.message)
    except AccountLockedError as e:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail=e.message)
    except InvalidCredentialsError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)
    except AuthException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=e.message)

@app.get("/api/v1/auth/me")
async def get_current_user_profile(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncSession = Depends(get_db)
):
    """
    Validates session token and returns active user (FLS-038).
    """
    if not cred or not cred.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    sm = SessionManager(db)
    try:
        user, sess = await sm.validate_session(cred.credentials)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "status": user.status.value,
            "session_id": sess.session_id
        }
    except InvalidSessionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)

@app.post("/api/v1/auth/rotate")
async def rotate_session(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncSession = Depends(get_db)
):
    """
    Session rotation (FLS-038): Invalidates old token and returns fresh session.
    """
    if not cred or not cred.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    sm = SessionManager(db)
    try:
        new_sess = await sm.rotate_session(cred.credentials)
        return {
            "success": True,
            "session_token": new_sess.session_token,
            "expires_at": new_sess.expires_at.isoformat()
        }
    except InvalidSessionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=e.message)

@app.post("/api/v1/auth/logout")
async def logout_user(
    cred: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer),
    db: AsyncSession = Depends(get_db)
):
    """
    Session revocation (FLS-038).
    """
    if not cred or not cred.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authorization token")
    sm = SessionManager(db)
    revoked = await sm.revoke_session(cred.credentials)
    return {"success": True, "revoked": revoked}

@app.get("/api/v1/users/{user_id}/limits/{sku_id}")
async def check_user_sku_limit(
    user_id: str,
    sku_id: str,
    max_limit: int = 2,
    db: AsyncSession = Depends(get_db)
):
    """
    Queries current allocated quantity and checks limit (FLS-032).
    """
    lm = UserLimitManager(db)
    allocated = await lm.get_user_allocated_quantity(user_id, sku_id)
    return {
        "user_id": user_id,
        "sku_id": sku_id,
        "allocated_quantity": allocated,
        "max_limit": max_limit,
        "remaining_allowance": max(0, max_limit - allocated),
        "is_limit_reached": allocated >= max_limit
    }

# ----------------- Flash-Sale API (FLS-103) -----------------

@app.post("/api/v1/sales", status_code=status.HTTP_201_CREATED)
async def create_flash_sale_campaign(
    schema: CampaignSchema,
    db: AsyncSession = Depends(get_db)
):
    cm = CampaignManager(db)
    try:
        created = await cm.create_campaign(schema)
        return created
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/api/v1/sales/{campaign_id}")
async def get_flash_sale_campaign(
    campaign_id: str,
    db: AsyncSession = Depends(get_db)
):
    cm = CampaignManager(db)
    camp = await cm.get_campaign(campaign_id)
    if not camp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Campaign '{campaign_id}' not found")
    return camp

@app.get("/api/v1/sales")
async def list_flash_sale_campaigns(
    db: AsyncSession = Depends(get_db)
):
    cm = CampaignManager(db)
    return await cm.list_campaigns()

# ----------------- Product API (FLS-104) -----------------

@app.post("/api/v1/products", status_code=status.HTTP_201_CREATED)
async def create_product(
    schema: ProductSchema,
    db: AsyncSession = Depends(get_db)
):
    pm = ProductManager(db)
    try:
        created = await pm.create_product(schema)
        return created
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/api/v1/products/{product_id}")
async def get_product(
    product_id: str,
    db: AsyncSession = Depends(get_db)
):
    pm = ProductManager(db)
    prod = await pm.get_product(product_id)
    if not prod:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Product '{product_id}' not found")
    return prod

@app.get("/api/v1/products")
async def list_products(
    db: AsyncSession = Depends(get_db)
):
    pm = ProductManager(db)
    return await pm.list_products()

# ----------------- Inventory API (FLS-105) -----------------

class InitInventoryRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    product_id: str = Field(..., min_length=1)
    total_allocated: int = Field(..., gt=0)

@app.post("/api/v1/inventory/initialize", status_code=status.HTTP_201_CREATED)
async def initialize_inventory(
    req: InitInventoryRequest,
    db: AsyncSession = Depends(get_db)
):
    im = InventoryManager(db)
    try:
        inv = await im.initialize_inventory(req.sku_id, req.product_id, req.total_allocated)
        return inv
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

@app.get("/api/v1/inventory/{sku_id}")
async def get_inventory_sku(
    sku_id: str,
    db: AsyncSession = Depends(get_db)
):
    im = InventoryManager(db)
    inv = await im.get_inventory(sku_id)
    if not inv:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"SKU '{sku_id}' not found")
    return inv

@app.get("/api/v1/inventory")
async def list_inventory(
    db: AsyncSession = Depends(get_db)
):
    im = InventoryManager(db)
    return await im.list_inventory()

# ----------------- Order API (FLS-109) -----------------

@app.get("/api/v1/orders/{order_id}")
async def get_order_by_id(
    order_id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(OrderRecord).where(OrderRecord.order_id == order_id)
    res = await db.execute(stmt)
    order = res.scalars().first()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Order '{order_id}' not found")
    return {
        "order_id": order.order_id,
        "user_id": order.user_id,
        "sku_id": order.sku_id,
        "quantity": order.quantity,
        "unit_price_cents": order.unit_price_cents,
        "total_amount_cents": order.total_amount_cents,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None
    }

@app.get("/api/v1/users/{user_id}/orders")
async def list_user_orders(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    stmt = select(OrderRecord).where(OrderRecord.user_id == user_id)
    res = await db.execute(stmt)
    orders = res.scalars().all()
    return [
        {
            "order_id": o.order_id,
            "user_id": o.user_id,
            "sku_id": o.sku_id,
            "quantity": o.quantity,
            "unit_price_cents": o.unit_price_cents,
            "total_amount_cents": o.total_amount_cents,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None
        }
        for o in orders
    ]

# ----------------- Queue API (FLS-111) -----------------

class QueueJoinRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    sku_id: str = Field(..., min_length=1)

class QueueAdmitRequest(BaseModel):
    sku_id: str = Field(..., min_length=1)
    batch_size: int = Field(default=10, gt=0)
    lease_seconds: int = Field(default=120, gt=0)

@app.post("/api/v1/queue/join")
async def join_waiting_room_queue(req: QueueJoinRequest):
    return global_waiting_room.join_queue(req.user_id, req.sku_id)

@app.get("/api/v1/queue/status")
async def get_queue_status(user_id: str, sku_id: str):
    return global_waiting_room.get_ticket_status(user_id, sku_id)

@app.post("/api/v1/queue/admit")
async def admit_waiting_room_batch(req: QueueAdmitRequest):
    admitted = global_waiting_room.admit_batch(req.sku_id, req.batch_size, req.lease_seconds)
    return {"sku_id": req.sku_id, "admitted_count": len(admitted), "admitted_tickets": admitted}

# ----------------- Observability: Prometheus & Incidents (FLS-127, FLS-135) -----------------

@app.get("/metrics")
async def get_prometheus_metrics(db: AsyncSession = Depends(get_db)):
    """
    Prometheus metrics exposition endpoint (FLS-127).
    """
    await refresh_inventory_gauges(db)
    content = export_metrics_text()
    return Response(content=content, media_type="text/plain; version=0.0.4; charset=utf-8")

@app.post("/api/v1/incidents/audit")
async def trigger_oversell_audit(sku_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    """
    Trigger real-time audit scan for stock conservation & oversell anomalies (FLS-135).
    """
    if sku_id:
        inc = await global_oversell_detector.audit_sku(db, sku_id)
        incidents = [inc] if inc else []
    else:
        incidents = await global_oversell_detector.audit_all_inventory(db)

    return {
        "status": "COMPLETED",
        "incidents_detected_count": len(incidents),
        "incidents": incidents
    }

@app.get("/api/v1/incidents/oversell")
async def get_oversell_incidents(sku_id: Optional[str] = None):
    """
    Retrieve logged oversell incidents (FLS-135).
    """
    return global_oversell_detector.get_incidents(sku_id)


