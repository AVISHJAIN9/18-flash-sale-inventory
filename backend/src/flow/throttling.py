"""
Request Throttling, Burst Handling, Per-SKU Limits, and Payment Timeout Handling.
Features:
- FLS-068: Per-SKU purchase limit
- FLS-072: Request throttling (token bucket rate limiter)
- FLS-073: Burst handling (burst capacity smoothing)
- FLS-077: Payment timeout handling (lease expiration and stock restoration)
"""

from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
import time
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.orders import OrderRecord, OrderStatus
from models.payments import PaymentRecord, PaymentStatus
from models.inventory import InventoryRecord, ReservationRecord, ReservationStatus

logger = logging.getLogger("flow.throttling")


class TokenBucketThrottler:
    """
    Token bucket rate limiter supporting burst handling and request throttling (FLS-072, FLS-073).
    """

    def __init__(self, rate_per_second: float = 20.0, burst_capacity: int = 50):
        self.rate_per_second = rate_per_second
        self.burst_capacity = burst_capacity
        # client_id -> {"tokens": float, "last_refill": float}
        self._buckets: Dict[str, Dict[str, float]] = {}

    def acquire(
        self,
        client_id: str,
        tokens_requested: int = 1,
        now: Optional[float] = None
    ) -> Tuple[bool, float]:
        """
        Attempts to acquire tokens.
        Returns:
            (allowed: bool, retry_after_seconds: float)
        """
        current_time = now if now is not None else time.time()

        if client_id not in self._buckets:
            self._buckets[client_id] = {
                "tokens": float(self.burst_capacity),
                "last_refill": current_time
            }

        bucket = self._buckets[client_id]
        elapsed = max(0.0, current_time - bucket["last_refill"])
        bucket["last_refill"] = current_time

        # Refill tokens according to elapsed time, capped at burst_capacity (FLS-073)
        refilled = elapsed * self.rate_per_second
        bucket["tokens"] = min(float(self.burst_capacity), bucket["tokens"] + refilled)

        if bucket["tokens"] >= tokens_requested:
            bucket["tokens"] -= tokens_requested
            return True, 0.0

        # Throttled (FLS-072): calculate wait time for required tokens
        needed = tokens_requested - bucket["tokens"]
        retry_after = needed / self.rate_per_second if self.rate_per_second > 0 else 1.0
        return False, round(retry_after, 3)

    def reset(self, client_id: Optional[str] = None):
        if client_id:
            self._buckets.pop(client_id, None)
        else:
            self._buckets.clear()


class PerSkuPurchaseLimiter:
    """
    Enforces per-SKU purchase and reservation limits (FLS-068).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def assert_within_sku_limit(
        self,
        user_id: str,
        sku_id: str,
        requested_quantity: int,
        max_sku_limit: int
    ) -> None:
        """
        Calculates cumulative items purchased or held by user for this SKU and enforces limit.
        """
        # Sum paid or pending orders
        order_stmt = (
            select(OrderRecord)
            .where(OrderRecord.user_id == user_id)
            .where(OrderRecord.sku_id == sku_id)
            .where(OrderRecord.status.in_([OrderStatus.PENDING.value, OrderStatus.PAID.value]))
        )
        order_res = await self.session.execute(order_stmt)
        total_ordered = sum(o.quantity for o in order_res.scalars().all())

        if total_ordered + requested_quantity > max_sku_limit:
            raise ValueError(
                f"Purchase of {requested_quantity} items exceeds per-SKU limit of {max_sku_limit} (already ordered/pending: {total_ordered})"
            )


class PaymentTimeoutManager:
    """
    Detects expired payment timeouts and releases held stock back to available pool (FLS-077).
    """
    def __init__(self, session: AsyncSession, default_timeout_seconds: int = 900):
        self.session = session
        self.default_timeout_seconds = default_timeout_seconds

    async def sweep_timed_out_payments(
        self,
        current_time: Optional[datetime] = None
    ) -> List[str]:
        """
        Cancels pending payments/orders exceeding timeout and restores held inventory.
        """
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        # Look for pending orders older than timeout
        stmt = (
            select(OrderRecord)
            .where(OrderRecord.status == OrderStatus.PENDING.value)
        )
        res = await self.session.execute(stmt)
        pending_orders = res.scalars().all()

        cancelled_order_ids: List[str] = []

        for order in pending_orders:
            order_created = order.created_at
            if order_created.tzinfo is None:
                order_created = order_created.replace(tzinfo=timezone.utc)

            age_seconds = (now - order_created).total_seconds()
            if age_seconds >= self.default_timeout_seconds:
                # 1. Cancel order
                order.status = OrderStatus.CANCELLED.value

                # 2. Release held stock back to available inventory
                inv_stmt = (
                    update(InventoryRecord)
                    .where(InventoryRecord.sku_id == order.sku_id)
                    .values(
                        available=InventoryRecord.available + order.quantity,
                        reserved=InventoryRecord.reserved - order.quantity
                    )
                )
                await self.session.execute(inv_stmt)

                cancelled_order_ids.append(order.order_id)
                logger.info(f"Order '{order.order_id}' timed out after {age_seconds}s and released {order.quantity} stock")

        if cancelled_order_ids:
            await self.session.commit()

        return cancelled_order_ids
