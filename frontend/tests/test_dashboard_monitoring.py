import os
import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base, get_db
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from models.campaigns import CampaignManager, CampaignSchema
from models.orders import OrderRecord
from api.app import app
import datetime

def test_FLS_115_dashboard_dom_and_assets():
    """
    FLS-115: Flash-sale dashboard DOM structure verification.
    Verifies that the dashboard overview, metrics grid, and connection indicators exist in index.html.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "src", "index.html")
    assert os.path.isfile(html_path)

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert "FlashSaleOps" in html or "Flash Sale" in html
    assert 'id="connection-status"' in html
    assert 'id="card-total"' in html
    assert 'id="card-available"' in html
    assert 'id="card-reserved"' in html
    assert 'id="card-sold"' in html
    assert 'id="card-sellthrough"' in html

def test_FLS_123_order_monitoring_dom():
    """
    FLS-123: Order monitoring panel DOM element verification.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "src", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="order-monitoring-panel"' in html
    assert 'id="order-monitoring-tbody"' in html

def test_FLS_125_real_time_counters_dom():
    """
    FLS-125: Real-time operational counters DOM element verification.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "src", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="counters-section"' in html
    assert 'id="val-orders-count"' in html
    assert 'id="val-total-gmv"' in html
    assert 'id="val-waiting-room"' in html

def test_FLS_126_low_stock_alerts_dom():
    """
    FLS-126: Low-stock alerts banner DOM element verification.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "src", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="low-stock-alerts-container"' in html
    assert 'id="alerts-count-badge"' in html
    assert 'id="alerts-list"' in html

@pytest_asyncio.fixture
async def dashboard_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        # Seed product
        p_mgr = ProductManager(session)
        await p_mgr.create_product(ProductSchema(product_id="prod-dash-100", title="Pro Gaming Console", original_price_cents=50000))
        # Seed inventory
        inv_mgr = InventoryManager(session)
        await inv_mgr.initialize_inventory("sku-dash-100", "prod-dash-100", total_allocated=20)
        # Seed order
        order = OrderRecord(
            order_id="ord-dash-001",
            user_id="user-dash-1",
            sku_id="sku-dash-100",
            quantity=2,
            unit_price_cents=45000,
            total_amount_cents=90000,
            idempotency_key="idemp-dash-001",
            status="CONFIRMED",
            created_at=datetime.datetime.now(datetime.timezone.utc)
        )
        session.add(order)
        await session.commit()

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_115_flash_sale_dashboard_summary_api(dashboard_client):
    """
    FLS-115: Verifies /api/v1/dashboard/summary endpoint aggregate statistics.
    """
    resp = await dashboard_client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "OPERATIONAL"
    assert data["total_allocated"] == 20
    assert data["total_available"] == 20
    assert data["total_orders"] == 1
    assert "sell_through_percentage" in data

@pytest.mark.asyncio
async def test_FLS_123_order_monitoring_api(dashboard_client):
    """
    FLS-123: Verifies /api/v1/dashboard/orders returns real-time order stream.
    """
    resp = await dashboard_client.get("/api/v1/dashboard/orders")
    assert resp.status_code == 200
    orders = resp.json()
    assert isinstance(orders, list)
    assert len(orders) >= 1
    ord0 = orders[0]
    assert ord0["order_id"] == "ord-dash-001"
    assert ord0["sku_id"] == "sku-dash-100"
    assert ord0["quantity"] == 2
    assert ord0["total_amount_cents"] == 90000
    assert ord0["status"] == "CONFIRMED"

@pytest.mark.asyncio
async def test_FLS_125_real_time_counters_api(dashboard_client):
    """
    FLS-125: Verifies /api/v1/dashboard/counters returns active metrics.
    """
    resp = await dashboard_client.get("/api/v1/dashboard/counters")
    assert resp.status_code == 200
    counters = resp.json()
    assert counters["total_allocated"] == 20
    assert counters["total_orders"] == 1
    assert counters["total_gmv_cents"] == 90000
    assert "waiting_room_active" in counters

@pytest.mark.asyncio
async def test_FLS_126_low_stock_alerts_api(dashboard_client):
    """
    FLS-126: Verifies /api/v1/dashboard/alerts triggers alert when stock is below threshold.
    """
    # Currently 20/20 available (100%), with default threshold 20% it shouldn't trigger
    resp = await dashboard_client.get("/api/v1/dashboard/alerts")
    assert resp.status_code == 200
    alerts = resp.json()
    # 20 available of 20 allocated is not low stock
    assert len(alerts) == 0

    # Test with high threshold to trigger alert
    resp_high = await dashboard_client.get("/api/v1/dashboard/alerts?threshold_pct=100.0")
    assert resp_high.status_code == 200
    alerts_high = resp_high.json()
    assert len(alerts_high) >= 1
    assert alerts_high[0]["sku_id"] == "sku-dash-100"
    assert alerts_high[0]["alert_level"] in ["WARNING", "CRITICAL"]
