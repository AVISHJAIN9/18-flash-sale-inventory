import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, ReservationStore
from transactions.atomic import AtomicTransactionCoordinator

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
async def test_FLS_011_atomic_transactions(async_session):
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-at-1", title="Console", original_price_cents=49900))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-at-1", "prod-at-1", total_allocated=10)

    coord = AtomicTransactionCoordinator(async_session)

    # 1. Successful atomic reservation of 3 units
    ok, msg, res = await coord.reserve_stock_atomic(
        sku_id="sku-at-1",
        user_id="user-atom-1",
        quantity=3,
        reservation_id="res-at-1",
        lease_seconds=300
    )
    assert ok is True
    assert res is not None

    # Check inventory updated atomically: available was 10, now 7; reserved is 3
    inv = await inv_mgr.get_inventory("sku-at-1")
    assert inv.available == 7
    assert inv.reserved == 3
    assert inv.available + inv.reserved + inv.sold == 10

    # 2. Failed atomic reservation attempt: requesting 8 units when only 7 available
    ok_fail, msg_fail, res_fail = await coord.reserve_stock_atomic(
        sku_id="sku-at-1",
        user_id="user-atom-2",
        quantity=8,
        reservation_id="res-at-2"
    )
    assert ok_fail is False
    assert "Insufficient stock" in msg_fail
    assert res_fail is None

    # Verify inventory was NOT modified (atomic rollback): available is STILL 7, reserved is STILL 3
    inv_after = await inv_mgr.get_inventory("sku-at-1")
    assert inv_after.available == 7
    assert inv_after.reserved == 3
