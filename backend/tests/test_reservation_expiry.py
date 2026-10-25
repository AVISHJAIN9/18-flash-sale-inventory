import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from clock import Clock
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, ReservationStatus
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
async def test_FLS_045_reservation_expiry(async_session):
    clk = Clock(initial_time=1000.0)

    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-exp", title="TV", original_price_cents=50000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-exp", "prod-exp", total_allocated=10)

    service = StockReservationService(async_session, clock=clk)

    # 1. Create a reservation with 60 second lease
    ok, _, data = await service.reserve_stock("sku-exp", "user-exp", quantity=4, lease_seconds=60)
    assert ok is True
    tok = data["reservation_token"]

    st1 = await service.get_stock_status("sku-exp")
    assert st1["available"] == 6
    assert st1["reserved"] == 4

    # 2. Advance clock 30s (T=1030): not expired yet
    clk.advance(30.0)
    expired = await service.expire_stale_reservations()
    assert len(expired) == 0
    st2 = await service.get_stock_status("sku-exp")
    assert st2["available"] == 6  # Still reserved

    # 3. Advance clock past lease (total 70s -> T=1070): expired!
    clk.advance(40.0)
    expired = await service.expire_stale_reservations()
    assert tok in expired

    # Stock is returned exactly once: available is back to 10, reserved is 0!
    st3 = await service.get_stock_status("sku-exp")
    assert st3["available"] == 10
    assert st3["reserved"] == 0

    # 4. Running reaper again does not double-return stock
    expired_again = await service.expire_stale_reservations()
    assert len(expired_again) == 0
    st4 = await service.get_stock_status("sku-exp")
    assert st4["available"] == 10
