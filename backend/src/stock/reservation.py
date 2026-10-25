"""
Real-time Stock Tracking and Atomic Reservation Service (FLS-039, FLS-044).
Enforces continuous invariant check: available + reserved + sold == total_allocated.
"""

from typing import Optional, Dict, Any, Tuple, List
from datetime import datetime, timezone, timedelta
import uuid
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.inventory import InventoryRecord, ReservationRecord, ReservationStatus
from clock import Clock

import asyncio

class StockReservationService:
    _sku_locks: Dict[str, asyncio.Lock] = {}

    @classmethod
    def _get_sku_lock(cls, sku_id: str) -> asyncio.Lock:
        if sku_id not in cls._sku_locks:
            cls._sku_locks[sku_id] = asyncio.Lock()
        return cls._sku_locks[sku_id]

    def __init__(self, session: AsyncSession, clock: Optional[Clock] = None):
        self.session = session
        self.clock = clock or Clock()

    async def get_stock_status(self, sku_id: str) -> Optional[Dict[str, Any]]:
        """Real-time stock query with conservation invariant validation (FLS-039)."""
        stmt = select(InventoryRecord).where(InventoryRecord.sku_id == sku_id)
        res = await self.session.execute(stmt)
        inv = res.scalar_one_or_none()
        if not inv:
            return None

        # Continuous invariant verification
        assert inv.available >= 0, f"Negative available stock detected for {sku_id}"
        assert inv.reserved >= 0, f"Negative reserved stock detected for {sku_id}"
        assert inv.sold >= 0, f"Negative sold stock detected for {sku_id}"
        assert inv.available + inv.reserved + inv.sold == inv.total_allocated, (
            f"Stock drift detected! available({inv.available}) + reserved({inv.reserved}) + "
            f"sold({inv.sold}) != total_allocated({inv.total_allocated})"
        )

        return {
            "sku_id": inv.sku_id,
            "product_id": inv.product_id,
            "available": inv.available,
            "reserved": inv.reserved,
            "sold": inv.sold,
            "total_allocated": inv.total_allocated,
            "is_in_stock": inv.available > 0
        }

    async def reserve_stock(
        self,
        sku_id: str,
        user_id: str,
        quantity: int = 1,
        lease_seconds: int = 300
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Atomic stock reservation (FLS-044).
        Atomically checks available >= quantity and updates available and reserved in a single query.
        """
        if quantity <= 0:
            return False, "Quantity must be positive", None

        async with self._get_sku_lock(sku_id):
            stmt = (
                update(InventoryRecord)
                .where(InventoryRecord.sku_id == sku_id)
                .where(InventoryRecord.available >= quantity)
                .values(
                    available=InventoryRecord.available - quantity,
                    reserved=InventoryRecord.reserved + quantity,
                    updated_at=datetime.now(timezone.utc)
                )
                .execution_options(synchronize_session="fetch")
            )
            res = await self.session.execute(stmt)

            if res.rowcount == 0:
                # Stock was insufficient or SKU did not exist
                return False, "Insufficient stock or SKU not found", None

            # Create persistent reservation record
            now_ts = self.clock.now()
            now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)
            expires_dt = now_dt + timedelta(seconds=lease_seconds)
            reservation_token = f"tok_{uuid.uuid4().hex[:16]}"
            rec = ReservationRecord(
                reservation_id=reservation_token,
                sku_id=sku_id,
                user_id=user_id,
                quantity=quantity,
                status=ReservationStatus.PENDING.value,
                expires_at=expires_dt,
                created_at=now_dt
            )
            self.session.add(rec)
            await self.session.commit()

            return True, "Reservation successful", {
                "reservation_token": reservation_token,
                "sku_id": sku_id,
                "user_id": user_id,
                "quantity": quantity,
                "expires_at": expires_dt.isoformat(),
                "status": ReservationStatus.PENDING.value
            }

    async def release_reservation(self, reservation_id: str) -> Tuple[bool, str]:
        """
        Explicitly releases a pending reservation (FLS-046).
        Restores reserved stock back to available stock.
        """
        stmt = select(ReservationRecord).where(ReservationRecord.reservation_id == reservation_id).with_for_update()
        res = await self.session.execute(stmt)
        rec = res.scalar_one_or_none()

        if not rec:
            return False, f"Reservation {reservation_id} not found"

        if rec.status != ReservationStatus.PENDING.value:
            return False, f"Cannot release reservation with status '{rec.status}'"

        rec.status = ReservationStatus.RELEASED.value

        # Return stock
        inv_stmt = (
            update(InventoryRecord)
            .where(InventoryRecord.sku_id == rec.sku_id)
            .values(
                available=InventoryRecord.available + rec.quantity,
                reserved=InventoryRecord.reserved - rec.quantity,
                updated_at=datetime.now(timezone.utc)
            )
        )
        await self.session.execute(inv_stmt)
        await self.session.commit()
        return True, "Reservation released successfully"

    async def expire_stale_reservations(self, current_time: Optional[datetime] = None) -> List[str]:
        """
        Scans for expired pending reservations and restores stock (FLS-045).
        Guarantees exact-once stock return per expired reservation.
        """
        now_dt = current_time or datetime.fromtimestamp(self.clock.now(), tz=timezone.utc)

        # Select all PENDING reservations whose expires_at <= now
        stmt = (
            select(ReservationRecord)
            .where(ReservationRecord.status == ReservationStatus.PENDING.value)
            .where(ReservationRecord.expires_at <= now_dt)
            .with_for_update()
        )
        res = await self.session.execute(stmt)
        stale_records = res.scalars().all()

        expired_ids = []
        for rec in stale_records:
            rec.status = ReservationStatus.EXPIRED.value
            expired_ids.append(rec.reservation_id)

            # Return reserved stock to available
            inv_stmt = (
                update(InventoryRecord)
                .where(InventoryRecord.sku_id == rec.sku_id)
                .values(
                    available=InventoryRecord.available + rec.quantity,
                    reserved=InventoryRecord.reserved - rec.quantity,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            await self.session.execute(inv_stmt)

        await self.session.commit()
        return expired_ids
