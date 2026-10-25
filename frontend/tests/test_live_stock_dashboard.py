import os
import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base, get_db
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from api.app import app

def test_FLS_116_dashboard_assets_integrity():
    """
    FLS-116: Live stock dashboard asset verification.
    Verifies that the HTML, CSS, and JavaScript files exist, contain required dashboard elements,
    metrics cards, and interactive reservation form.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "src", "index.html")
    css_path = os.path.join(base_dir, "src", "index.css")
    js_path = os.path.join(base_dir, "src", "app.js")

    assert os.path.isfile(html_path), "index.html missing"
    assert os.path.isfile(css_path), "index.css missing"
    assert os.path.isfile(js_path), "app.js missing"

    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()

    # Verify key dashboard UI components
    assert "Live Stock Dashboard" in html
    assert 'id="val-total"' in html
    assert 'id="val-available"' in html
    assert 'id="val-reserved"' in html
    assert 'id="val-sold"' in html
    assert 'id="val-sellthrough"' in html
    assert 'id="inventory-tbody"' in html
    assert 'id="reserve-form"' in html
    assert 'id="submit-reserve-btn"' in html

@pytest_asyncio.fixture
async def test_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        p_mgr = ProductManager(session)
        await p_mgr.create_product(ProductSchema(product_id="prod-dash-1", title="Dashboard Drone", original_price_cents=45000))
        inv_mgr = InventoryManager(session)
        await inv_mgr.initialize_inventory("sku-dash-1", "prod-dash-1", total_allocated=10)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_116_dashboard_api_feed(test_client):
    """
    FLS-116: Live stock dashboard API feed verification.
    Verifies that GET /api/v1/dashboard/stock supplies the live feed consumed by the frontend.
    """
    resp = await test_client.get("/api/v1/dashboard/stock")
    assert resp.status_code == 200
    feed = resp.json()
    assert isinstance(feed, list)
    assert len(feed) >= 1
    item = feed[0]
    assert item["sku_id"] == "sku-dash-1"
    assert item["total_allocated"] == 10
    assert item["available"] == 10
    assert item["reserved"] == 0
    assert item["sold"] == 0
    assert item["in_stock"] is True
    assert item["sell_through_percentage"] == 0.0
