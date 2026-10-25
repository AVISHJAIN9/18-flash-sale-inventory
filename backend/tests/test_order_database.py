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
async def test_FLS_004_order_database_and_idempotency(async_session):
    # Setup product and inventory
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-gpu-1", title="RTX 4090", original_price_cents=159900))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-gpu-4090", "prod-gpu-1", total_allocated=10)

    order_mgr = OrderManager(async_session)

    # 1. Create order
    order = await order_mgr.create_order(
        order_id="ord-001",
        user_id="user-buyer-1",
        sku_id="sku-gpu-4090",
        quantity=1,
        unit_price_cents=159900,
        idempotency_key="idemp-key-ord-1"
    )
    assert order.order_id == "ord-001"
    assert order.total_amount_cents == 159900
    assert order.status == OrderStatus.PENDING.value

    # 2. Idempotency test: repeated submission with identical idempotency_key returns identical order
    dup_order = await order_mgr.create_order(
        order_id="ord-002-attempt",
        user_id="user-buyer-1",
        sku_id="sku-gpu-4090",
        quantity=1,
        unit_price_cents=159900,
        idempotency_key="idemp-key-ord-1"
    )
    assert dup_order.order_id == "ord-001"  # Returns original order without creating duplicate!

    # 3. List orders for buyer
    orders = await order_mgr.list_orders_by_user("user-buyer-1")
    assert len(orders) == 1
