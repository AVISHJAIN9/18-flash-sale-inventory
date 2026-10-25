import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import update
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, InventoryRecord
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
async def test_FLS_048_negative_stock_prevention(async_session):
    """
    FLS-048: Negative-stock prevention.
    Verifies that neither normal operations nor illegal negative modifications can violate
    the non-negative stock invariant (available >= 0, reserved >= 0, sold >= 0).
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-neg-check", title="Test Item", original_price_cents=5000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-neg-check", "prod-neg-check", total_allocated=3)

    service = StockReservationService(async_session)

    # 1. Normal reservation consumes up to total (3 units)
    ok, msg, data = await service.reserve_stock("sku-neg-check", "user-1", quantity=3)
    assert ok is True
    st = await service.get_stock_status("sku-neg-check")
    assert st["available"] == 0

    # 2. Service level prevention: attempting to reserve even 1 unit fails cleanly
    ok2, msg2, data2 = await service.reserve_stock("sku-neg-check", "user-2", quantity=1)
    assert ok2 is False
    assert "Insufficient stock" in msg2

    # Verify stock stayed strictly at 0 (never negative)
    st2 = await service.get_stock_status("sku-neg-check")
    assert st2["available"] == 0
    assert st2["reserved"] == 3

    # 3. Database CHECK constraint level prevention:
    # Directly attempting an update to force available < 0 must raise IntegrityError
    with pytest.raises(IntegrityError):
        stmt = (
            update(InventoryRecord)
            .where(InventoryRecord.sku_id == "sku-neg-check")
            .values(available=-1)
        )
        await async_session.execute(stmt)
        await async_session.commit()

    await async_session.rollback()

    # Re-verify stock remains valid and non-negative
    st3 = await service.get_stock_status("sku-neg-check")
    assert st3["available"] == 0
    assert st3["reserved"] == 3
    assert st3["total_allocated"] == 3
