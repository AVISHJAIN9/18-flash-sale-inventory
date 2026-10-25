"""
Atomic Transactions Coordinator for Inventory & Order operations (FLS-011).
Guarantees all-or-nothing multi-table operations with automatic rollback on constraint violations.
"""

from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.inventory import InventoryRecord, ReservationRecord, ReservationStatus
from models.orders import OrderRecord, OrderStatus

class AtomicTransactionCoordinator:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def reserve_stock_atomic(
        self,
        sku_id: str,
        user_id: str,
        quantity: int,
        reservation_id: str,
        lease_seconds: int = 300
    ) -> Tuple[bool, str, Optional[ReservationRecord]]:
        """
        Atomically decrements available stock and creates a reservation (FLS-011).
        If stock is insufficient or database constraints fail, rolls back cleanly.
        """
        if quantity <= 0:
            return False, "Quantity must be positive", None

        try:
            async with self.session.begin_nested():
                # Lock inventory row FOR UPDATE
                stmt = select(InventoryRecord).where(InventoryRecord.sku_id == sku_id).with_for_update()
                res = await self.session.execute(stmt)
                inv = res.scalar_one_or_none()

                if not inv:
                    return False, f"SKU {sku_id} not found", None

                if inv.available < quantity:
                    return False, f"Insufficient stock: requested {quantity}, available {inv.available}", None

                # Update stock conservation counters
                inv.available -= quantity
                inv.reserved += quantity
                inv.updated_at = datetime.now(timezone.utc)

                # Create reservation record
                expires = datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
                rec = ReservationRecord(
                    reservation_id=reservation_id,
                    sku_id=sku_id,
                    user_id=user_id,
                    quantity=quantity,
                    status=ReservationStatus.PENDING.value,
                    expires_at=expires,
                    created_at=datetime.now(timezone.utc)
                )
                self.session.add(rec)

            await self.session.commit()
            return True, "Reservation created atomically", rec
        except Exception as e:
            await self.session.rollback()
            return False, f"Transaction aborted: {str(e)}", None
