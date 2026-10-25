import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from models.orders import OrderManager, OrderStatus, OrderStateMachine

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
async def test_FLS_091_order_state_machine(async_session):
    """
    FLS-091: Order state machine.
    Enforces deterministic state transitions for orders:
    PENDING -> PAID -> REFUNDED (valid)
    PENDING -> CANCELLED (valid)
    Illegal transitions (e.g. CANCELLED -> PAID, REFUNDED -> PENDING) raise ValueError.
    """
    # 1. State machine table unit validation
    assert OrderStateMachine.can_transition(OrderStatus.PENDING, OrderStatus.PAID) is True
    assert OrderStateMachine.can_transition(OrderStatus.PENDING, OrderStatus.CANCELLED) is True
    assert OrderStateMachine.can_transition(OrderStatus.PENDING, OrderStatus.EXPIRED) is True
    assert OrderStateMachine.can_transition(OrderStatus.PAID, OrderStatus.REFUNDED) is True

    # Illegal transitions
    assert OrderStateMachine.can_transition(OrderStatus.CANCELLED, OrderStatus.PAID) is False
    assert OrderStateMachine.can_transition(OrderStatus.EXPIRED, OrderStatus.PAID) is False
    assert OrderStateMachine.can_transition(OrderStatus.REFUNDED, OrderStatus.PENDING) is False

    # 2. Database backed order transition lifecycle
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-osm-1", title="State Item", original_price_cents=5000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-osm-1", "prod-osm-1", total_allocated=10)

    order_mgr = OrderManager(async_session)
    order = await order_mgr.create_order(
        order_id="ord-osm-1",
        user_id="user-osm",
        sku_id="sku-osm-1",
        quantity=1,
        unit_price_cents=5000,
        idempotency_key="osm-key-1"
    )
    assert order.status == OrderStatus.PENDING.value

    # PENDING -> PAID succeeds
    paid_order = await order_mgr.transition_order_status("ord-osm-1", OrderStatus.PAID)
    assert paid_order.status == OrderStatus.PAID.value

    # PAID -> REFUNDED succeeds
    refunded_order = await order_mgr.transition_order_status("ord-osm-1", OrderStatus.REFUNDED)
    assert refunded_order.status == OrderStatus.REFUNDED.value

    # REFUNDED is a terminal state -> attempting to transition to PAID must raise ValueError
    with pytest.raises(ValueError) as exc:
        await order_mgr.transition_order_status("ord-osm-1", OrderStatus.PAID)
    assert "Illegal order state transition" in str(exc.value)
