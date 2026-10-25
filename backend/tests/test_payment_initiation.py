import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from models.orders import OrderManager
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
async def test_FLS_092_payment_initiation(async_session):
    """
    FLS-092: Payment initiation.
    Verifies recording an initiated payment against an order, amount validation in integer cents,
    and initial INITIATED status.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-pay-init", title="Item", original_price_cents=7500))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-pay-init", "prod-pay-init", total_allocated=5)

    order_mgr = OrderManager(async_session)
    order = await order_mgr.create_order(
        order_id="ord-pay-init-1",
        user_id="user-1",
        sku_id="sku-pay-init",
        quantity=1,
        unit_price_cents=7500,
        idempotency_key="key-pay-init-1"
    )

    pay_mgr = PaymentManager(async_session)

    # 1. Successful payment initiation
    pay = await pay_mgr.record_payment(
        payment_id="pay-init-1",
        order_id=order.order_id,
        payment_provider="stripe",
        amount_cents=7500,
        idempotency_key="pay-idem-init-1",
        status=PaymentStatus.INITIATED
    )
    assert pay.payment_id == "pay-init-1"
    assert pay.order_id == "ord-pay-init-1"
    assert pay.amount_cents == 7500
    assert pay.status == PaymentStatus.INITIATED.value
    assert pay.payment_provider == "stripe"

    # 2. Negative amount rejected
    with pytest.raises(ValueError):
        await pay_mgr.record_payment(
            payment_id="pay-bad-amt",
            order_id=order.order_id,
            payment_provider="stripe",
            amount_cents=-100,
            idempotency_key="pay-bad-key"
        )
