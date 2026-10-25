import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from stock.reservation import StockReservationService

@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_039_real_time_stock_tracking(async_session):
    # Setup SKU with 200 units
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-watch-1", title="Smart Watch", original_price_cents=25000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-watch-1", "prod-watch-1", total_allocated=200)

    service = StockReservationService(async_session)

    # Query real-time stock
    status = await service.get_stock_status("sku-watch-1")
    assert status is not None
    assert status["total_allocated"] == 200
    assert status["available"] == 200
    assert status["reserved"] == 0
    assert status["sold"] == 0
    assert status["is_in_stock"] is True

    # Reserve 25 units
    ok, _, _ = await service.reserve_stock("sku-watch-1", "user-1", quantity=25)
    assert ok is True

    # Real-time stock status reflects reservation immediately
    status2 = await service.get_stock_status("sku-watch-1")
    assert status2["available"] == 175
    assert status2["reserved"] == 25
    assert status2["sold"] == 0
    assert status2["total_allocated"] == 200
