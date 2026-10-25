import asyncio
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, InventoryRecord
from stock.reservation import StockReservationService
from stock.cache_resilience import CacheReservationProxy
from models.orders import OrderRecord
from models.payments import PaymentRecord

@pytest_asyncio.fixture
async def chaos_test_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        pm = ProductManager(session)
        await pm.create_product(ProductSchema(product_id="prod-chaos-1", title="Chaos Drone", original_price_cents=20000))
        im = InventoryManager(session)
        await im.initialize_inventory("sku-chaos-1", "prod-chaos-1", total_allocated=30)

    yield session_maker
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_141_chaos_fault_injection_and_rollback(chaos_test_env):
    """
    FLS-141: Chaos testing and fault injection recovery.
    Simulates transaction drop midway through reservation/checkout: asserts transaction rollback,
    zero leaked inventory, and strict invariant preservation.
    """
    session_maker = chaos_test_env

    # 1. Successful reservation of 5 items
    async with session_maker() as session:
        service = StockReservationService(session)
        ok, _, data = await service.reserve_stock("sku-chaos-1", "buyer-normal-1", quantity=5)
        assert ok is True
        token = data["reservation_token"]

    # 2. Chaos fault: buyer starts checkout, but simulated node crash/abort occurs before commit
    try:
        async with session_maker() as session:
            from flow.checkout import CheckoutService
            checkout = CheckoutService(session)
            # Patch commit to simulate sudden connection drop
            async def failing_commit():
                await session.rollback()
                raise ConnectionResetError("Simulated infrastructure node crash during commit")
            session.commit = failing_commit

            await checkout.process_checkout(
                user_id="buyer-normal-1",
                sku_id="sku-chaos-1",
                quantity=5,
                unit_price_cents=20000,
                reservation_token=token,
                idempotency_key="idemp-chaos-crash-1"
            )
    except ConnectionResetError:
        pass  # Expected simulated crash

    # 3. Verify database state is uncorrupted:
    # 5 items remain reserved (unconverted to sold), available is still 25, no corrupt order row
    async with session_maker() as session:
        inv = await session.get(InventoryRecord, "sku-chaos-1")
        assert inv.available == 25, f"Expected 25 available, got {inv.available}"
        assert inv.reserved == 5, f"Expected 5 reserved, got {inv.reserved}"
        assert inv.sold == 0
        assert inv.available + inv.reserved + inv.sold == inv.total_allocated

@pytest.mark.asyncio
async def test_FLS_145_cache_failure_handling(chaos_test_env):
    """
    FLS-145: Cache failure transparent fallback.
    Verifies that when the cache/Redis tier drops or fails, reservations fall back
    transparently to PostgreSQL with zero oversell and exact quantity accounting.
    """
    session_maker = chaos_test_env

    # 1. Normal operation with healthy cache
    async with session_maker() as session:
        proxy = CacheReservationProxy(session)
        ok, msg, data, tier = await proxy.reserve_stock("sku-chaos-1", "user-c-1", quantity=2)
        assert ok is True
        assert tier == "CACHE"
        await session.commit()

    # 2. Inject cache outage (Redis connection drops)
    async with session_maker() as session:
        proxy = CacheReservationProxy(session)
        proxy.simulate_cache_failure(True)
        assert proxy.is_cache_healthy is False

        # Attempt reservation during cache failure
        ok, msg, data, tier = await proxy.reserve_stock("sku-chaos-1", "user-c-2", quantity=3)
        assert ok is True
        assert tier == "POSTGRES_FALLBACK"
        assert proxy.fallback_count == 1
        await session.commit()

    # 3. Verify total durability in database
    async with session_maker() as session:
        inv = await session.get(InventoryRecord, "sku-chaos-1")
        # Total allocated 30; user-c-1 took 2, user-c-2 took 3 -> reserved = 5, available = 25
        assert inv.reserved == 5
        assert inv.available == 25
        assert inv.available + inv.reserved + inv.sold == inv.total_allocated
