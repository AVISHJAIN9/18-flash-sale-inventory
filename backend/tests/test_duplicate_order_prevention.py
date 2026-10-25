import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from stock.reservation import StockReservationService
from flow.checkout import CheckoutService

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
async def test_FLS_071_duplicate_order_prevention(async_session):
    """
    FLS-071: Duplicate-order prevention.
    Verifies that:
    1. Re-attempting checkout on an already-confirmed reservation is rejected.
    2. Submitting duplicate orders with the same idempotency key does not create second order records.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-dup-chk", title="Console", original_price_cents=49900))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-dup-chk", "prod-dup-chk", total_allocated=10)

    stock_svc = StockReservationService(async_session)
    checkout_svc = CheckoutService(async_session)

    # Reserve 1 unit
    ok_res, _, res_data = await stock_svc.reserve_stock("sku-dup-chk", "buyer-dup", quantity=1)
    assert ok_res is True
    tok = res_data["reservation_token"]

    # 1. First checkout succeeds
    ok1, msg1, data1 = await checkout_svc.process_checkout(
        user_id="buyer-dup",
        sku_id="sku-dup-chk",
        quantity=1,
        unit_price_cents=49900,
        reservation_token=tok,
        idempotency_key="unique-order-key-1"
    )
    assert ok1 is True
    assert data1["is_replay"] is False
    order_id = data1["order_id"]

    # 2. Attempting to use the SAME reservation token with a NEW idempotency key fails (reservation already CONFIRMED)
    ok2, msg2, data2 = await checkout_svc.process_checkout(
        user_id="buyer-dup",
        sku_id="sku-dup-chk",
        quantity=1,
        unit_price_cents=49900,
        reservation_token=tok,
        idempotency_key="different-order-key-2"
    )
    assert ok2 is False
    assert "Cannot checkout reservation with status 'CONFIRMED'" in msg2
    assert data2 is None

    # 3. Same idempotency key returns idempotent replay without creating new order
    ok3, msg3, data3 = await checkout_svc.process_checkout(
        user_id="buyer-dup",
        sku_id="sku-dup-chk",
        quantity=1,
        unit_price_cents=49900,
        reservation_token=tok,
        idempotency_key="unique-order-key-1"
    )
    assert ok3 is True
    assert data3["is_replay"] is True
    assert data3["order_id"] == order_id

    # Verify inventory was decremented exactly once
    st = await stock_svc.get_stock_status("sku-dup-chk")
    assert st["sold"] == 1
    assert st["available"] == 9
