"""
Optimistic Concurrency Control with Bounded Retries (FLS-012).
Guarantees conflict resolution and zero lost updates under concurrent modifications (§9 Invariant).
"""

import asyncio
import logging
from typing import Callable, TypeVar, Optional, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.inventory import InventoryRecord

logger = logging.getLogger(__name__)

T = TypeVar("T")


class OptimisticConcurrencyError(Exception):
    """Raised when an update encounters conflicting concurrent writes exceeding max retries."""
    pass


async def update_inventory_optimistic(
    session: AsyncSession,
    sku_id: str,
    quantity_to_reserve: int,
    max_retries: int = 5,
    backoff_seconds: float = 0.01,
    _conflict_injector: Optional[Any] = None
) -> InventoryRecord:
    """
    Reserves stock using optimistic concurrency control (version matching).
    Retries up to max_retries with exponential backoff on version conflicts.
    Guarantees conservation and prevents lost updates under high concurrency (§9 Invariant).
    """
    for attempt in range(1, max_retries + 1):
        # 1. Fetch current record and version
        stmt = select(InventoryRecord).where(InventoryRecord.sku_id == sku_id)
        result = await session.execute(stmt)
        record = result.scalars().first()

        if not record:
            raise ValueError(f"SKU '{sku_id}' not found in inventory")

        if record.available < quantity_to_reserve:
            raise ValueError(f"Insufficient stock for SKU '{sku_id}'. Available: {record.available}, Requested: {quantity_to_reserve}")

        current_version = record.version
        new_available = record.available - quantity_to_reserve
        new_reserved = record.reserved + quantity_to_reserve
        new_version = current_version + 1

        if _conflict_injector is not None:
            if asyncio.iscoroutinefunction(_conflict_injector):
                await _conflict_injector()
            else:
                _conflict_injector()

        # 2. Conditional atomic update with version check
        update_stmt = (
            update(InventoryRecord)
            .where(
                InventoryRecord.sku_id == sku_id,
                InventoryRecord.version == current_version
            )
            .values(
                available=new_available,
                reserved=new_reserved,
                version=new_version
            )
        )
        update_res = await session.execute(update_stmt)
        await session.commit()

        if update_res.rowcount == 1:
            # Successful atomic write!
            await session.refresh(record)
            return record

        # Conflict detected! Rollback and retry
        await session.rollback()
        logger.debug(f"Optimistic conflict on SKU '{sku_id}' attempt {attempt}/{max_retries}")
        if attempt < max_retries:
            await asyncio.sleep(backoff_seconds * (2 ** (attempt - 1)))  # exponential backoff delay on conflict

    raise OptimisticConcurrencyError(
        f"Optimistic concurrency update for SKU '{sku_id}' failed after {max_retries} attempts due to write conflicts."
    )
