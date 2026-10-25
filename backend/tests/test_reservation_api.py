import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base, get_db
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from api.app import app

@pytest_asyncio.fixture
async def test_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Pre-populate product and inventory
    async with session_maker() as session:
        p_mgr = ProductManager(session)
        await p_mgr.create_product(ProductSchema(product_id="prod-api-1", title="API Phone", original_price_cents=79900))
        inv_mgr = InventoryManager(session)
        await inv_mgr.initialize_inventory("sku-api-1", "prod-api-1", total_allocated=3)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_106_reservation_api(test_client):
    """
    FLS-106: Reservation API.
    Tests POST /api/v1/reservations for successful atomic reservation and 409 Conflict on exhaustion.
    """
    # 1. Successful reservation of 2 units
    payload = {
        "sku_id": "sku-api-1",
        "user_id": "api-buyer-1",
        "quantity": 2,
        "lease_seconds": 300
    }
    resp = await test_client.post("/api/v1/reservations", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "reservation_token" in data["reservation"]
    assert data["reservation"]["quantity"] == 2

    # 2. Check stock endpoint returns remaining 1 available
    stock_resp = await test_client.get("/api/v1/stock/sku-api-1")
    assert stock_resp.status_code == 200
    st = stock_resp.json()
    assert st["available"] == 1
    assert st["reserved"] == 2

    # 3. Requesting 2 more units fails with 409 Conflict (only 1 left)
    resp2 = await test_client.post("/api/v1/reservations", json=payload)
    assert resp2.status_code == 409
    assert "Insufficient stock" in resp2.json()["detail"]
