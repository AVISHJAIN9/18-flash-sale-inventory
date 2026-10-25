import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
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
async def test_FLS_097_order_expiration(async_session):
    """
    FLS-097: Order expiration.
    Scans for unpaid pending orders exceeding payment window and marks them EXPIRED.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-ord-exp", title="Flash Gadget", original_price_cents=10000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-ord-exp", "prod-ord-exp", total_allocated=10)

    order_mgr = OrderManager(async_session)
    order = await order_mgr.create_order(
        order_id="ord-exp-1",
        user_id="user-slow",
        sku_id="sku-ord-exp",
        quantity=2,
        unit_price_cents=10000,
        idempotency_key="key-ord-exp-1"
    )
    assert order.status == OrderStatus.PENDING.value

    # 1. Running reaper with future time beyond timeout (e.g. 1000s later)
    now = datetime.now(timezone.utc)
    future_time = now + timedelta(seconds=1200)

    expired_ids = await order_mgr.expire_stale_orders(timeout_seconds=900, current_time=future_time)
    assert "ord-exp-1" in expired_ids

    # 2. Verify order state is now EXPIRED
    updated = await order_mgr.get_order("ord-exp-1")
    assert updated.status == OrderStatus.EXPIRED.value
