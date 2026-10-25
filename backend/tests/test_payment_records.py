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
async def test_FLS_005_payment_records_and_idempotency(async_session):
    # Setup order
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-p-1", title="Phone", original_price_cents=80000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-p-1", "prod-p-1", total_allocated=5)
    ord_mgr = OrderManager(async_session)
    order = await ord_mgr.create_order("ord-pay-1", "user-pay-1", "sku-p-1", 1, 80000, "idemp-ord-pay-1")

    pay_mgr = PaymentManager(async_session)

    # 1. Record payment
    payment = await pay_mgr.record_payment(
        payment_id="pay-001",
        order_id="ord-pay-1",
        payment_provider="gateway-sandbox",
        amount_cents=80000,
        idempotency_key="idemp-pay-1",
        status=PaymentStatus.SUCCESS,
        provider_payment_id="ch_sandbox_123"
    )
    assert payment.payment_id == "pay-001"
    assert payment.amount_cents == 80000
    assert payment.status == PaymentStatus.SUCCESS.value

    # 2. Duplicate payment submission with same idempotency key returns original charge (no double charge!)
    dup_pay = await pay_mgr.record_payment(
        payment_id="pay-002-attempt",
        order_id="ord-pay-1",
        payment_provider="gateway-sandbox",
        amount_cents=80000,
        idempotency_key="idemp-pay-1",
        status=PaymentStatus.SUCCESS
    )
    assert dup_pay.payment_id == "pay-001"
