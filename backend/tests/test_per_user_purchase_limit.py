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
async def test_FLS_067_per_user_purchase_limit(async_session):
    """
    FLS-067: Per-user purchase limit.
    Enforces that a user cannot purchase more than the configured maximum quota (e.g. 2 units),
    even if stock is available.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-limited", title="Hot Sneaker", original_price_cents=15000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-limited", "prod-limited", total_allocated=20)

    stock_svc = StockReservationService(async_session)
    checkout_svc = CheckoutService(async_session)

    # User reserves and purchases 2 units (max limit is 2)
    ok_res, _, res_data = await stock_svc.reserve_stock("sku-limited", "buyer-whale", quantity=2)
    assert ok_res is True
    tok1 = res_data["reservation_token"]

    ok_chk, msg_chk, data_chk = await checkout_svc.process_checkout(
        user_id="buyer-whale",
        sku_id="sku-limited",
        quantity=2,
        unit_price_cents=15000,
        reservation_token=tok1,
        idempotency_key="chk-whale-1",
        max_quantity_per_user=2
    )
    assert ok_chk is True
    assert data_chk["status"] == "PAID"

    # User attempts to reserve and purchase another 1 unit -> rejected by user quota check!
    ok_res2, _, res_data2 = await stock_svc.reserve_stock("sku-limited", "buyer-whale", quantity=1)
    assert ok_res2 is True
    tok2 = res_data2["reservation_token"]

    ok_chk2, msg_chk2, data_chk2 = await checkout_svc.process_checkout(
        user_id="buyer-whale",
        sku_id="sku-limited",
        quantity=1,
        unit_price_cents=15000,
        reservation_token=tok2,
        idempotency_key="chk-whale-2",
        max_quantity_per_user=2
    )
    assert ok_chk2 is False
    assert "Purchase limit exceeded" in msg_chk2
    assert data_chk2 is None
