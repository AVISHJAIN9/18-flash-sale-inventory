import asyncio
import time
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, InventoryRecord
from stock.reservation import StockReservationService

@pytest_asyncio.fixture
async def load_test_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        pm = ProductManager(session)
        await pm.create_product(ProductSchema(product_id="prod-load-1", title="Load Test Drone", original_price_cents=10000))
        im = InventoryManager(session)
        await im.initialize_inventory("sku-load-1", "prod-load-1", total_allocated=100)

    yield session_maker
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_139_concurrent_load_testing(load_test_env):
    """
    FLS-139: High-concurrency load testing and latency measurement.
    Measures requests/sec throughput and p95 latency under concurrent reservation pressure.
    Guarantees zero oversell and strict conservation invariant.
    """
    session_maker = load_test_env
    num_concurrent_buyers = 50
    items_per_buyer = 2  # Total demand: 100 items (exact inventory)

    latencies = []

    async def buyer_task(buyer_idx: int):
        t0 = time.perf_counter()
        async with session_maker() as session:
            service = StockReservationService(session)
            success, msg, data = await service.reserve_stock(
                sku_id="sku-load-1",
                user_id=f"buyer-load-{buyer_idx}",
                quantity=items_per_buyer,
                lease_seconds=300
            )
            await session.commit()
        t1 = time.perf_counter()
        latencies.append((t1 - t0) * 1000.0)  # ms
        return success, msg

    start_wall = time.perf_counter()
    tasks = [buyer_task(i) for i in range(num_concurrent_buyers)]
    results = await asyncio.gather(*tasks)
    total_time = time.perf_counter() - start_wall

    successful = [r for r in results if r[0] is True]
    failed = [r for r in results if r[0] is False]

    assert len(successful) == 50, f"Expected 50 successful reservations, got {len(successful)}"
    assert len(failed) == 0

    # Calculate throughput and percentiles
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    rps = num_concurrent_buyers / total_time if total_time > 0 else 0

    print(f"\n[LOAD TEST BENCHMARK] Total Requests: {num_concurrent_buyers}, Time: {total_time:.3f}s")
    print(f"Throughput: {rps:.1f} req/s | p50: {p50:.2f}ms | p95: {p95:.2f}ms | p99: {p99:.2f}ms")

    # Invariant verification in DB
    async with session_maker() as session:
        inv = await session.get(InventoryRecord, "sku-load-1")
        assert inv.available == 0
        assert inv.reserved == 100
        assert inv.sold == 0
        assert inv.available + inv.reserved + inv.sold == inv.total_allocated

    # Now attempt 10 extra reservations when stock is depleted - all must be rejected
    extra_tasks = [buyer_task(100 + i) for i in range(10)]
    extra_results = await asyncio.gather(*extra_tasks)
    extra_success = [r for r in extra_results if r[0] is True]
    assert len(extra_success) == 0, "Oversell occurred! Extra reservations succeeded when depleted."
