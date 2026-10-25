import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, ReservationRecord, ReservationStatus
from stock.reservation import StockReservationService
from flow.checkout import CheckoutService
from clock import DeterministicClock
from sqlalchemy import select

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
async def test_FLS_076_checkout_timeout(async_session):
    """
    FLS-076: Checkout timeout.
    Verifies that if a user does not complete checkout within the reservation lease,
    checkout attempts fail, the reservation transitions to EXPIRED, and stock is restored.
    """
    clock = DeterministicClock(initial_time=1700000000.0)
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-timeout", title="Timed Item", original_price_cents=10000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-timeout", "prod-timeout", total_allocated=5)

    stock_svc = StockReservationService(async_session, clock=clock)
    checkout_svc = CheckoutService(async_session, clock=clock)

    # 1. Buyer reserves 2 units with 60 second lease
    ok, _, data = await stock_svc.reserve_stock("sku-timeout", "buyer-slow", quantity=2, lease_seconds=60)
    assert ok is True
    token = data["reservation_token"]

    st_res = await stock_svc.get_stock_status("sku-timeout")
    assert st_res["available"] == 3
    assert st_res["reserved"] == 2

    # 2. Advance time past the 60s lease (e.g. 75 seconds later)
    clock.advance(75.0)

    # 3. Attempting checkout must fail due to checkout timeout
    ok_chk, msg_chk, data_chk = await checkout_svc.process_checkout(
        user_id="buyer-slow",
        sku_id="sku-timeout",
        quantity=2,
        unit_price_cents=10000,
        reservation_token=token,
        idempotency_key="slow-checkout-attempt"
    )
    assert ok_chk is False
    assert "checkout timeout" in msg_chk.lower() or "expired" in msg_chk.lower()

    # 4. Verify reservation was marked EXPIRED in the database
    res_rec = await async_session.scalar(select(ReservationRecord).where(ReservationRecord.reservation_id == token))
    assert res_rec.status == ReservationStatus.EXPIRED.value

    # 5. Verify stock was safely restored: available returns to 5, reserved returns to 0
    st_restored = await stock_svc.get_stock_status("sku-timeout")
    assert st_restored["available"] == 5
    assert st_restored["reserved"] == 0
    assert st_restored["sold"] == 0
