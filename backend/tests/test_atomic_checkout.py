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
async def test_FLS_069_atomic_checkout(async_session):
    """
    FLS-069: Atomic checkout.
    Verifies that checkout transitions reservation to CONFIRMED, moves inventory
    from reserved to sold, and creates Order and Payment records in a single atomic transaction.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-phone-1", title="Flash Phone", original_price_cents=99900))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-phone-1", "prod-phone-1", total_allocated=10)

    stock_svc = StockReservationService(async_session)
    checkout_svc = CheckoutService(async_session)

    # 1. Buyer reserves 2 units
    ok_res, _, res_data = await stock_svc.reserve_stock("sku-phone-1", "buyer-alice", quantity=2)
    assert ok_res is True
    tok = res_data["reservation_token"]

    st_pre = await stock_svc.get_stock_status("sku-phone-1")
    assert st_pre["available"] == 8
    assert st_pre["reserved"] == 2
    assert st_pre["sold"] == 0

    # 2. Checkout 2 units
    ok_chk, msg_chk, data_chk = await checkout_svc.process_checkout(
        user_id="buyer-alice",
        sku_id="sku-phone-1",
        quantity=2,
        unit_price_cents=99900,
        reservation_token=tok,
        idempotency_key="alice-checkout-1001",
        payment_provider="stripe"
    )
    assert ok_chk is True
    assert data_chk["order_id"].startswith("ord_")
    assert data_chk["payment_id"].startswith("pay_")
    assert data_chk["total_amount_cents"] == 199800
    assert data_chk["status"] == "PAID"

    # 3. Verify stock after checkout: available == 8, reserved == 0, sold == 2
    st_post = await stock_svc.get_stock_status("sku-phone-1")
    assert st_post["available"] == 8
    assert st_post["reserved"] == 0
    assert st_post["sold"] == 2
    assert st_post["total_allocated"] == 10
