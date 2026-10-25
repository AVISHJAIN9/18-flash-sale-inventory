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
async def test_FLS_096_payment_idempotency(async_session):
    """
    FLS-096: Payment idempotency.
    Verifies that calling record_payment with the same idempotency key returns the existing payment
    record without creating a duplicate record or double billing.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-pay-idem", title="Item", original_price_cents=8000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-pay-idem", "prod-pay-idem", total_allocated=5)

    order_mgr = OrderManager(async_session)
    order = await order_mgr.create_order(
        order_id="ord-pay-idem-1",
        user_id="user-1",
        sku_id="sku-pay-idem",
        quantity=1,
        unit_price_cents=8000,
        idempotency_key="key-pay-idem-1"
    )

    pay_mgr = PaymentManager(async_session)
    idempotency_key = "unique-payment-token-777888"

    # 1. First record_payment succeeds
    pay1 = await pay_mgr.record_payment(
        payment_id="pay-idem-1",
        order_id=order.order_id,
        payment_provider="stripe",
        amount_cents=8000,
        idempotency_key=idempotency_key
    )
    assert pay1.payment_id == "pay-idem-1"
    assert pay1.idempotency_key == idempotency_key

    # 2. Second record_payment with identical idempotency key returns pay1
    pay2 = await pay_mgr.record_payment(
        payment_id="pay-idem-2-ignored",
        order_id=order.order_id,
        payment_provider="stripe",
        amount_cents=8000,
        idempotency_key=idempotency_key
    )
    assert pay2.payment_id == "pay-idem-1"
    assert pay2.idempotency_key == idempotency_key

    # 3. Lookup by idempotency key
    found = await pay_mgr.get_payment_by_idempotency(idempotency_key)
    assert found is not None
    assert found.payment_id == "pay-idem-1"
