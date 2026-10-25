"""
Tests for High-Concurrency Purchase Flow:
- FLS-068: Per-SKU purchase limit
- FLS-072: Request throttling
- FLS-073: Burst handling
- FLS-077: Payment timeout handling
"""

import pytest
import pytest_asyncio
import time
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base
from models.catalog import ProductRecord
from models.inventory import InventoryRecord, InventoryManager
from models.orders import OrderRecord, OrderStatus
from flow.throttling import (
    TokenBucketThrottler,
    PerSkuPurchaseLimiter,
    PaymentTimeoutManager
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_FLS_068_per_sku_purchase_limit(db_session):
    """
    FLS-068: Per-SKU purchase limit (BE, P0).
    Verifies (§9 Invariant):
    - Per-SKU limits hold across cumulative orders
    - Purchases exceeding SKU limit raise error
    """
    # Seed product & inventory & orders
    prod = ProductRecord(product_id="prod-sku-lim-1", title="Console Special Edition", original_price_cents=49900)
    inv = InventoryRecord(
        sku_id="sku-console-special",
        product_id="prod-sku-lim-1",
        total_allocated=10,
        available=8,
        reserved=2,
        sold=0,
        version=1
    )
    db_session.add(prod)
    db_session.add(inv)

    # User already has 1 completed order and 1 pending order for this SKU
    order1 = OrderRecord(
        order_id="ord-sku-lim-1",
        user_id="gamer_vip",
        sku_id="sku-console-special",
        quantity=1,
        unit_price_cents=49900,
        total_amount_cents=49900,
        status=OrderStatus.PAID.value,
        idempotency_key="idemp-sku-1"
    )
    order2 = OrderRecord(
        order_id="ord-sku-lim-2",
        user_id="gamer_vip",
        sku_id="sku-console-special",
        quantity=1,
        unit_price_cents=49900,
        total_amount_cents=49900,
        status=OrderStatus.PENDING.value,
        idempotency_key="idemp-sku-2"
    )
    db_session.add(order1)
    db_session.add(order2)
    await db_session.commit()

    limiter = PerSkuPurchaseLimiter(db_session)

    # Limit is 2 items -> User already has 2 items -> requesting 1 more must reject
    with pytest.raises(ValueError) as exc:
        await limiter.assert_within_sku_limit(
            user_id="gamer_vip",
            sku_id="sku-console-special",
            requested_quantity=1,
            max_sku_limit=2
        )
    assert "exceeds per-SKU limit of 2" in str(exc.value)

    # Different user with 0 orders can purchase within limit
    await limiter.assert_within_sku_limit(
        user_id="gamer_new",
        sku_id="sku-console-special",
        requested_quantity=2,
        max_sku_limit=2
    )


def test_FLS_072_request_throttling():
    """
    FLS-072: Request throttling (BE, P0).
    Verifies:
    - Sustained request throttling when token bucket is exhausted
    - Accurate calculation of retry_after seconds
    - Recovery after time interval passes
    """
    throttler = TokenBucketThrottler(rate_per_second=10.0, burst_capacity=5)
    clock = 1000.0

    # 1. Exhaust 5 tokens immediately
    for _ in range(5):
        allowed, retry_after = throttler.acquire("client-ip-1", tokens_requested=1, now=clock)
        assert allowed is True
        assert retry_after == 0.0

    # 2. 6th request at the same clock time is throttled
    allowed_throttled, retry_after = throttler.acquire("client-ip-1", tokens_requested=1, now=clock)
    assert allowed_throttled is False
    assert retry_after == 0.1  # 1 token / 10 tokens per sec = 0.1s

    # 3. Advance clock by 0.15s (1.5 tokens refilled) -> Request succeeds
    allowed_later, retry_later = throttler.acquire("client-ip-1", tokens_requested=1, now=clock + 0.15)
    assert allowed_later is True
    assert retry_later == 0.0


def test_FLS_073_burst_handling():
    """
    FLS-073: Burst handling (BE, P0).
    Verifies:
    - High-velocity initial burst up to configured burst capacity succeeds without drops
    - Immediate excess beyond burst capacity is throttled
    - Token smoothing behavior across refill windows
    """
    # 50 req/sec steady rate with burst allowance up to 30 requests
    throttler = TokenBucketThrottler(rate_per_second=50.0, burst_capacity=30)
    clock = 2000.0

    # Burst of 30 simultaneous requests
    for i in range(30):
        allowed, _ = throttler.acquire("burst-client", tokens_requested=1, now=clock)
        assert allowed is True, f"Burst request {i+1} failed"

    # Request 31 exceeds burst capacity
    allowed_burst_overflow, wait_sec = throttler.acquire("burst-client", tokens_requested=1, now=clock)
    assert allowed_burst_overflow is False
    assert wait_sec > 0.0

    # Advance clock by 0.2s (10 tokens refilled at 50 tokens/sec)
    for _ in range(10):
        allowed_refill, _ = throttler.acquire("burst-client", tokens_requested=1, now=clock + 0.2)
        assert allowed_refill is True


@pytest.mark.asyncio
async def test_FLS_077_payment_timeout_handling(db_session):
    """
    FLS-077: Payment timeout handling (BE, P0).
    Verifies (§9 Invariant):
    - Unpaid pending order past timeout window is cancelled
    - Held inventory stock is automatically released back to available pool
    - Conservation invariant holds before and after sweep
    """
    prod = ProductRecord(product_id="prod-timeout-1", title="Timeout Watch", original_price_cents=30000)
    db_session.add(prod)

    # Initial inventory: total=10, available=8, reserved=2, sold=0
    inv = InventoryRecord(
        sku_id="sku-timeout-watch",
        product_id="prod-timeout-1",
        total_allocated=10,
        available=8,
        reserved=2,
        sold=0,
        version=1
    )
    db_session.add(inv)

    base_time = datetime(2026, 11, 20, 14, 0, 0, tzinfo=timezone.utc)

    # Order created 20 minutes ago (timeout is 15 minutes = 900 seconds)
    order = OrderRecord(
        order_id="ord-timed-out-1",
        user_id="slow_buyer",
        sku_id="sku-timeout-watch",
        quantity=2,
        unit_price_cents=30000,
        total_amount_cents=60000,
        status=OrderStatus.PENDING.value,
        idempotency_key="idemp-timeout-1",
        created_at=base_time - timedelta(minutes=20)
    )
    db_session.add(order)
    await db_session.commit()

    manager = PaymentTimeoutManager(db_session, default_timeout_seconds=900)

    # Sweep timed-out payments at base_time
    cancelled_ids = await manager.sweep_timed_out_payments(current_time=base_time)
    assert "ord-timed-out-1" in cancelled_ids

    # Verify order status transitioned to CANCELLED
    updated_order = (await db_session.execute(
        select(OrderRecord).where(OrderRecord.order_id == "ord-timed-out-1")
    )).scalars().first()
    assert updated_order.status == OrderStatus.CANCELLED.value

    # Verify inventory stock was restored to available pool
    updated_inv = (await db_session.execute(
        select(InventoryRecord).where(InventoryRecord.sku_id == "sku-timeout-watch")
    )).scalars().first()
    assert updated_inv.available == 10
    assert updated_inv.reserved == 0
    assert updated_inv.sold == 0
    assert updated_inv.available + updated_inv.reserved + updated_inv.sold == 10
