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
async def test_FLS_044_atomic_stock_reservation(async_session):
    # Setup inventory with exactly 5 units
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-rare-1", title="Limited Edition Shoe", original_price_cents=30000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-shoe-1", "prod-rare-1", total_allocated=5)

    service = StockReservationService(async_session)

    # 1. First reservation of 3 units -> succeeds
    ok1, msg1, data1 = await service.reserve_stock("sku-shoe-1", "user-res-1", quantity=3)
    assert ok1 is True
    assert "reservation_token" in data1
    assert data1["quantity"] == 3

    # Stock available is now 2
    st1 = await service.get_stock_status("sku-shoe-1")
    assert st1["available"] == 2
    assert st1["reserved"] == 3

    # 2. Second reservation of 2 units -> succeeds (reaches 0 available)
    ok2, msg2, data2 = await service.reserve_stock("sku-shoe-1", "user-res-2", quantity=2)
    assert ok2 is True

    st2 = await service.get_stock_status("sku-shoe-1")
    assert st2["available"] == 0
    assert st2["reserved"] == 5

    # 3. Third reservation of 1 unit -> fails atomically (no stock left!)
    ok3, msg3, data3 = await service.reserve_stock("sku-shoe-1", "user-res-3", quantity=1)
    assert ok3 is False
    assert "Insufficient stock" in msg3
    assert data3 is None

    # Verify inventory was NOT decremented below 0
    st3 = await service.get_stock_status("sku-shoe-1")
    assert st3["available"] == 0
    assert st3["reserved"] == 5
