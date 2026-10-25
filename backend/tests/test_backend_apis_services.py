"""
Integration Tests for Backend APIs & Services:
- FLS-103: Flash-sale API
- FLS-104: Product API
- FLS-105: Inventory API
- FLS-109: Order API
- FLS-111: Queue API
"""

import pytest
import pytest_asyncio
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base, get_db
from models.catalog import ProductRecord
from models.inventory import InventoryRecord
from models.orders import OrderRecord, OrderStatus
from api.app import app


@pytest_asyncio.fixture
async def api_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {
            "client": client,
            "session_maker": session_maker
        }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_FLS_104_product_api(api_client):
    """
    FLS-104: Product API (BE, P0).
    Verifies POST /api/v1/products, GET /api/v1/products/{id}, GET /api/v1/products
    """
    client = api_client["client"]

    # 1. Create product
    create_resp = await client.post("/api/v1/products", json={
        "product_id": "prod-api-1",
        "title": "Ultra Gaming Rig",
        "description": "High performance gaming PC",
        "original_price_cents": 249900
    })
    assert create_resp.status_code == 201, create_resp.text
    p = create_resp.json()
    assert p["product_id"] == "prod-api-1"
    assert p["original_price_cents"] == 249900

    # 2. Get product
    get_resp = await client.get("/api/v1/products/prod-api-1")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Ultra Gaming Rig"

    # 3. List products
    list_resp = await client.get("/api/v1/products")
    assert list_resp.status_code == 200
    prods = list_resp.json()
    assert any(x["product_id"] == "prod-api-1" for x in prods)


@pytest.mark.asyncio
async def test_FLS_105_inventory_api(api_client):
    """
    FLS-105: Inventory API (BE, P0).
    Verifies POST /api/v1/inventory/initialize, GET /api/v1/inventory/{sku_id}, GET /api/v1/inventory
    """
    client = api_client["client"]

    # Seed product first
    await client.post("/api/v1/products", json={
        "product_id": "prod-inv-api",
        "title": "Wireless Earbuds",
        "original_price_cents": 9900
    })

    # 1. Initialize inventory
    init_resp = await client.post("/api/v1/inventory/initialize", json={
        "sku_id": "sku-earbuds-white",
        "product_id": "prod-inv-api",
        "total_allocated": 100
    })
    assert init_resp.status_code == 201, init_resp.text
    inv = init_resp.json()
    assert inv["sku_id"] == "sku-earbuds-white"
    assert inv["available"] == 100

    # 2. Get inventory SKU
    get_resp = await client.get("/api/v1/inventory/sku-earbuds-white")
    assert get_resp.status_code == 200
    inv_get = get_resp.json()
    assert inv_get["available"] == 100
    assert inv_get["reserved"] == 0

    # 3. List inventory
    list_resp = await client.get("/api/v1/inventory")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 1


@pytest.mark.asyncio
async def test_FLS_103_flash_sale_api(api_client):
    """
    FLS-103: Flash-sale API (BE, P0).
    Verifies POST /api/v1/sales, GET /api/v1/sales/{id}, GET /api/v1/sales
    """
    client = api_client["client"]

    # Seed product and inventory
    await client.post("/api/v1/products", json={
        "product_id": "prod-sale-api",
        "title": "Cyber Drone",
        "original_price_cents": 50000
    })
    await client.post("/api/v1/inventory/initialize", json={
        "sku_id": "sku-drone-black",
        "product_id": "prod-sale-api",
        "total_allocated": 50
    })

    now = datetime.now(timezone.utc)
    start = now + timedelta(hours=1)
    end = start + timedelta(hours=3)

    # 1. Create sale campaign
    sale_resp = await client.post("/api/v1/sales", json={
        "campaign_id": "camp-black-friday-drone",
        "title": "Black Friday Cyber Drone Launch",
        "sku_id": "sku-drone-black",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "sale_price_cents": 35000,
        "allocated_stock": 50,
        "per_user_limit": 1
    })
    assert sale_resp.status_code == 201, sale_resp.text
    camp = sale_resp.json()
    assert camp["campaign_id"] == "camp-black-friday-drone"
    assert camp["sale_price_cents"] == 35000

    # 2. Get sale campaign
    get_resp = await client.get("/api/v1/sales/camp-black-friday-drone")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "Black Friday Cyber Drone Launch"

    # 3. List campaigns
    list_resp = await client.get("/api/v1/sales")
    assert list_resp.status_code == 200
    assert any(c["campaign_id"] == "camp-black-friday-drone" for c in list_resp.json())


@pytest.mark.asyncio
async def test_FLS_109_order_api(api_client):
    """
    FLS-109: Order API (BE, P0).
    Verifies GET /api/v1/orders/{order_id} and GET /api/v1/users/{user_id}/orders
    """
    client = api_client["client"]
    sm = api_client["session_maker"]

    # Seed product, inventory, and order
    async with sm() as session:
        p = ProductRecord(product_id="prod-ord-api", title="Smart TV", original_price_cents=75000)
        inv = InventoryRecord(sku_id="sku-tv-65", product_id="prod-ord-api", total_allocated=10, available=9, reserved=0, sold=1, version=1)
        ord1 = OrderRecord(
            order_id="ord-api-test-1",
            user_id="user_tv_fan",
            sku_id="sku-tv-65",
            quantity=1,
            unit_price_cents=75000,
            total_amount_cents=75000,
            status=OrderStatus.PAID.value,
            idempotency_key="idemp-tv-1"
        )
        session.add(p)
        session.add(inv)
        session.add(ord1)
        await session.commit()

    # 1. Query order by ID
    get_ord = await client.get("/api/v1/orders/ord-api-test-1")
    assert get_ord.status_code == 200
    o = get_ord.json()
    assert o["order_id"] == "ord-api-test-1"
    assert o["status"] == "PAID"
    assert o["total_amount_cents"] == 75000

    # 2. List user orders
    user_ords = await client.get("/api/v1/users/user_tv_fan/orders")
    assert user_ords.status_code == 200
    assert len(user_ords.json()) == 1


@pytest.mark.asyncio
async def test_FLS_111_queue_api(api_client):
    """
    FLS-111: Queue API (BE, P0).
    Verifies POST /api/v1/queue/join, GET /api/v1/queue/status, POST /api/v1/queue/admit
    """
    client = api_client["client"]

    # 1. Join queue
    join_resp = await client.post("/api/v1/queue/join", json={
        "user_id": "queue_buyer_42",
        "sku_id": "sku-drop-exclusive"
    })
    assert join_resp.status_code == 200
    j = join_resp.json()
    assert j["user_id"] == "queue_buyer_42"
    assert j["status"] == "QUEUED"
    assert j["position"] == 1

    # 2. Get status
    status_resp = await client.get("/api/v1/queue/status?user_id=queue_buyer_42&sku_id=sku-drop-exclusive")
    assert status_resp.status_code == 200
    s = status_resp.json()
    assert s["status"] == "QUEUED"

    # 3. Admit batch
    admit_resp = await client.post("/api/v1/queue/admit", json={
        "sku_id": "sku-drop-exclusive",
        "batch_size": 5,
        "lease_seconds": 180
    })
    assert admit_resp.status_code == 200
    adm = admit_resp.json()
    assert adm["admitted_count"] == 1
    assert adm["admitted_tickets"][0]["user_id"] == "queue_buyer_42"
    assert adm["admitted_tickets"][0]["status"] == "ADMITTED"
