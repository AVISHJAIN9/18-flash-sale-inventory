import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from models.orders import OrderManager, OrderStatus
from models.payments import PaymentManager, PaymentStatus

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
async def test_FLS_093_payment_confirmation(async_session):
    """
    FLS-093: Payment confirmation.
    Transitions payment status from INITIATED to SUCCESS, updates provider payment ID,
    and transitions associated order to PAID.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-pay-conf", title="Item", original_price_cents=4500))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-pay-conf", "prod-pay-conf", total_allocated=5)

    order_mgr = OrderManager(async_session)
    order = await order_mgr.create_order(
        order_id="ord-pay-conf-1",
        user_id="user-1",
        sku_id="sku-pay-conf",
        quantity=1,
        unit_price_cents=4500,
        idempotency_key="key-pay-conf-1"
    )
    assert order.status == OrderStatus.PENDING.value

    pay_mgr = PaymentManager(async_session)
    pay = await pay_mgr.record_payment(
        payment_id="pay-conf-1",
        order_id=order.order_id,
        payment_provider="adyen",
        amount_cents=4500,
        idempotency_key="idem-pay-conf-1",
        status=PaymentStatus.INITIATED
    )

    # Confirm payment
    confirmed = await pay_mgr.confirm_payment(
        payment_id="pay-conf-1",
        provider_payment_id="adyen_tx_99881122"
    )
    assert confirmed.status == PaymentStatus.SUCCESS.value
    assert confirmed.provider_payment_id == "adyen_tx_99881122"

    # Verify associated order is now PAID
    updated_order = await order_mgr.get_order("ord-pay-conf-1")
    assert updated_order.status == OrderStatus.PAID.value

    # Idempotent re-confirmation returns success cleanly
    reconfirmed = await pay_mgr.confirm_payment(
        payment_id="pay-conf-1",
        provider_payment_id="adyen_tx_99881122"
    )
    assert reconfirmed.status == PaymentStatus.SUCCESS.value
