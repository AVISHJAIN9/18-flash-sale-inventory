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
async def test_FLS_070_idempotency_keys(async_session):
    """
    FLS-070: Idempotency keys.
    Verifies that replaying a checkout with an identical idempotency key returns the original
    order record without creating duplicate orders or double-decrementing stock.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-watch", title="Flash Watch", original_price_cents=25000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-watch", "prod-watch", total_allocated=5)

    stock_svc = StockReservationService(async_session)
    checkout_svc = CheckoutService(async_session)

    # 1. Initial reservation
    ok_res, _, res_data = await stock_svc.reserve_stock("sku-watch", "buyer-bob", quantity=1)
    assert ok_res is True
    tok = res_data["reservation_token"]

    idem_key = "idem-key-unique-998877"

    # 2. First checkout attempt -> succeeds
    ok1, msg1, data1 = await checkout_svc.process_checkout(
        user_id="buyer-bob",
        sku_id="sku-watch",
        quantity=1,
        unit_price_cents=25000,
        reservation_token=tok,
        idempotency_key=idem_key
    )
    assert ok1 is True
    assert data1["is_replay"] is False
    first_order_id = data1["order_id"]

    # 3. Second checkout attempt with identical idempotency key -> idempotent replay
    ok2, msg2, data2 = await checkout_svc.process_checkout(
        user_id="buyer-bob",
        sku_id="sku-watch",
        quantity=1,
        unit_price_cents=25000,
        reservation_token=tok,
        idempotency_key=idem_key
    )
    assert ok2 is True
    assert data2["is_replay"] is True
    assert data2["order_id"] == first_order_id
    assert "idempotent replay" in msg2.lower()

    # 4. Verify inventory was only sold ONCE (sold == 1, not 2)
    st = await stock_svc.get_stock_status("sku-watch")
    assert st["sold"] == 1
    assert st["available"] == 4
    assert st["reserved"] == 0
