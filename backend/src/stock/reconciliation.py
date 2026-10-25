"""
Stock Reconciliation Engine (FLS-049).
Audits and reconciles inventory counts against underlying reservation ledger and confirmed orders.
Enforces the absolute conservation invariant: available + reserved + sold == total_allocated.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.inventory import InventoryRecord, ReservationRecord, ReservationStatus
from models.orders import OrderRecord, OrderStatus
from clock import Clock

class StockReconciliationService:
    def __init__(self, session: AsyncSession, clock: Optional[Clock] = None):
        self.session = session
        self.clock = clock or Clock()

    async def audit_sku(self, sku_id: str) -> Dict[str, Any]:
        """
        Audits current SKU inventory record against the ground-truth ledger of reservations and orders.
        """
        stmt = select(InventoryRecord).where(InventoryRecord.sku_id == sku_id)
        res = await self.session.execute(stmt)
        inv = res.scalar_one_or_none()
        if not inv:
            raise ValueError(f"SKU '{sku_id}' not found in inventory")

        now_ts = self.clock.now()
        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)

        # 1. Sum of currently active PENDING reservations
        active_res_stmt = (
            select(func.coalesce(func.sum(ReservationRecord.quantity), 0))
            .where(ReservationRecord.sku_id == sku_id)
            .where(ReservationRecord.status == ReservationStatus.PENDING.value)
            .where(ReservationRecord.expires_at > now_dt)
        )
        active_reserved = await self.session.scalar(active_res_stmt) or 0

        # 2. Sum of CONFIRMED reservations / completed orders
        confirmed_res_stmt = (
            select(func.coalesce(func.sum(ReservationRecord.quantity), 0))
            .where(ReservationRecord.sku_id == sku_id)
            .where(ReservationRecord.status == ReservationStatus.CONFIRMED.value)
        )
        confirmed_reserved = await self.session.scalar(confirmed_res_stmt) or 0

        # Also check OrderRecord for confirmed/paid orders
        order_sold_stmt = (
            select(func.coalesce(func.sum(OrderRecord.quantity), 0))
            .where(OrderRecord.sku_id == sku_id)
            .where(OrderRecord.status == OrderStatus.PAID.value)
        )
        orders_sold = await self.session.scalar(order_sold_stmt) or 0
        actual_sold = max(confirmed_reserved, orders_sold)

        # Expected available stock
        expected_available = inv.total_allocated - active_reserved - actual_sold

        has_discrepancy = (
            inv.reserved != active_reserved or
            inv.sold != actual_sold or
            inv.available != expected_available
        )

        return {
            "sku_id": sku_id,
            "total_allocated": inv.total_allocated,
            "recorded": {
                "available": inv.available,
                "reserved": inv.reserved,
                "sold": inv.sold
            },
            "ledger_truth": {
                "expected_available": expected_available,
                "active_reserved": active_reserved,
                "actual_sold": actual_sold
            },
            "discrepancy": {
                "available_delta": inv.available - expected_available,
                "reserved_delta": inv.reserved - active_reserved,
                "sold_delta": inv.sold - actual_sold
            },
            "has_discrepancy": has_discrepancy,
            "is_conserved": (inv.available + inv.reserved + inv.sold) == inv.total_allocated
        }

    async def reconcile_sku(self, sku_id: str) -> Dict[str, Any]:
        """
        Reconciles SKU inventory to ground truth, updating the record atomically and logging the audit diff.
        """
        audit = await self.audit_sku(sku_id)

        if not audit["has_discrepancy"]:
            return {
                "status": "IN_SYNC",
                "message": "No drift detected, inventory matches ledger truth exactly",
                "audit": audit
            }

        # Apply correction to inventory record
        truth = audit["ledger_truth"]
        stmt = (
            update(InventoryRecord)
            .where(InventoryRecord.sku_id == sku_id)
            .values(
                available=truth["expected_available"],
                reserved=truth["active_reserved"],
                sold=truth["actual_sold"],
                updated_at=datetime.now(timezone.utc)
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()

        # Re-verify post-correction
        reverified = await self.audit_sku(sku_id)
        assert not reverified["has_discrepancy"], "Reconciliation failed to eliminate drift"

        return {
            "status": "RECONCILED",
            "message": "Inventory drift successfully corrected to ledger truth",
            "previous": audit["recorded"],
            "corrected": reverified["recorded"]
        }
