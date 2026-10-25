import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base, get_db
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from stock.reservation import StockReservationService
from api.app import app

@pytest_asyncio.fixture
async def test_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Pre-populate product, inventory, and valid reservation
    reservation_token = None
    async with session_maker() as session:
        p_mgr = ProductManager(session)
        await p_mgr.create_product(ProductSchema(product_id="prod-chk-api", title="API Laptop", original_price_cents=120000))
        inv_mgr = InventoryManager(session)
        await inv_mgr.initialize_inventory("sku-chk-api", "prod-chk-api", total_allocated=5)
        stock_svc = StockReservationService(session)
        ok, _, res_data = await stock_svc.reserve_stock("sku-chk-api", "user-chk-api", quantity=1)
        assert ok is True
        reservation_token = res_data["reservation_token"]

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        client.reservation_token = reservation_token
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_108_checkout_api(test_client):
    """
    FLS-108: Checkout API.
    Tests POST /api/v1/checkout endpoint executing atomic purchase and returning order details.
    """
    tok = test_client.reservation_token

    payload = {
        "user_id": "user-chk-api",
        "sku_id": "sku-chk-api",
        "quantity": 1,
        "unit_price_cents": 120000,
        "reservation_token": tok,
        "idempotency_key": "api-checkout-key-5544"
    }

    # 1. Successful checkout
    resp = await test_client.post("/api/v1/checkout", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    order = data["order"]
    assert order["order_id"].startswith("ord_")
    assert order["status"] == "PAID"
    assert order["total_amount_cents"] == 120000

    # 2. Replay with same idempotency key -> 200 with idempotent replay flag
    resp_replay = await test_client.post("/api/v1/checkout", json=payload)
    assert resp_replay.status_code == 200
    assert resp_replay.json()["order"]["is_replay"] is True

    # 3. Invalid checkout with bad reservation token -> 400 Bad Request
    bad_payload = dict(payload)
    bad_payload["reservation_token"] = "tok_non_existent"
    bad_payload["idempotency_key"] = "api-bad-key-1"
    resp_bad = await test_client.post("/api/v1/checkout", json=bad_payload)
    assert resp_bad.status_code == 400
