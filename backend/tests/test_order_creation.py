import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from models.orders import OrderManager, OrderStatus

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
async def test_FLS_090_order_creation(async_session):
    """
    FLS-090: Order creation.
    Validates proper order record creation, total amount calculation in cents,
    initial PENDING status, and positive quantity/price validation.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-order-1", title="Orderable Product", original_price_cents=12000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-order-1", "prod-order-1", total_allocated=10)

    order_mgr = OrderManager(async_session)

    # 1. Valid order creation
    order = await order_mgr.create_order(
        order_id="ord-create-1",
        user_id="user-order-1",
        sku_id="sku-order-1",
        quantity=3,
        unit_price_cents=12000,
        idempotency_key="idem-order-create-1"
    )
    assert order.order_id == "ord-create-1"
    assert order.user_id == "user-order-1"
    assert order.sku_id == "sku-order-1"
    assert order.quantity == 3
    assert order.unit_price_cents == 12000
    assert order.total_amount_cents == 36000
    assert order.status == OrderStatus.PENDING.value

    # 2. Re-query order by ID
    fetched = await order_mgr.get_order("ord-create-1")
    assert fetched is not None
    assert fetched.total_amount_cents == 36000

    # 3. Invalid quantities and prices rejected
    with pytest.raises(ValueError):
        await order_mgr.create_order(
            order_id="ord-bad-qty",
            user_id="user-1",
            sku_id="sku-order-1",
            quantity=0,
            unit_price_cents=12000,
            idempotency_key="bad-qty"
        )

    with pytest.raises(ValueError):
        await order_mgr.create_order(
            order_id="ord-bad-price",
            user_id="user-1",
            sku_id="sku-order-1",
            quantity=1,
            unit_price_cents=-500,
            idempotency_key="bad-price"
        )
