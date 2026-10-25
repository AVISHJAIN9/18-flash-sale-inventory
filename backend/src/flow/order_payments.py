"""
Order Lifecycle, Payment Resilience, Refunds, and Inventory Consistency Service.
Features:
- FLS-094: Payment failure handling
- FLS-095: Payment retry (idempotent, single charge)
- FLS-098: Order cancellation with inventory stock release
- FLS-099: Refund initiation (idempotent, cap <= captured amount)
- FLS-100: Refund status tracking
- FLS-101: Inventory-to-order consistency audit job
"""

from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone
import uuid
import logging
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from models.orders import OrderRecord, OrderStatus, OrderStateMachine
from models.payments import PaymentRecord, PaymentStatus, RefundRecord, RefundStatus
from models.inventory import InventoryRecord

logger = logging.getLogger("flow.order_payments")


class OrderPaymentService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def handle_payment_failure(
        self,
        order_id: str,
        payment_id: str,
        error_code: str,
        error_message: str = ""
    ) -> PaymentRecord:
        """
        Records payment failure (FLS-094).
        Updates payment status to FAILED with error code.
        """
        stmt = select(PaymentRecord).where(PaymentRecord.payment_id == payment_id)
        res = await self.session.execute(stmt)
        payment = res.scalars().first()
        if not payment:
            raise ValueError(f"Payment '{payment_id}' not found")

        payment.status = PaymentStatus.FAILED.value
        payment.error_code = error_code
        payment.updated_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def retry_payment_idempotent(
        self,
        order_id: str,
        idempotency_key: str,
        payment_provider: str = "stripe_flash_gateway",
        simulated_charge_success: bool = True
    ) -> Tuple[bool, str, PaymentRecord]:
        """
        Idempotent payment retry (FLS-095).
        Guarantees: If payment already succeeded, returns it immediately without re-charging (§9 Invariant).
        """
        # 1. Check if payment with this idempotency key already exists
        stmt = select(PaymentRecord).where(PaymentRecord.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        existing = res.scalars().first()
        if existing and existing.status == PaymentStatus.SUCCESS.value:
            return True, "Payment already succeeded (idempotent replay)", existing

        # 2. Verify order is PENDING
        order_stmt = select(OrderRecord).where(OrderRecord.order_id == order_id)
        order_res = await self.session.execute(order_stmt)
        order = order_res.scalars().first()
        if not order:
            raise ValueError(f"Order '{order_id}' not found")
        if order.status == OrderStatus.PAID.value:
            # Order is already paid! Return existing payment if found
            if existing:
                return True, "Order already paid", existing
            raise ValueError(f"Order '{order_id}' is already paid")

        # 3. Create or update payment attempt
        now = datetime.now(timezone.utc)
        if not existing:
            payment_id = f"pay_{uuid.uuid4().hex[:12]}"
            payment = PaymentRecord(
                payment_id=payment_id,
                order_id=order_id,
                payment_provider=payment_provider,
                amount_cents=order.total_amount_cents,
                status=PaymentStatus.INITIATED.value,
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now
            )
            self.session.add(payment)
        else:
            payment = existing

        if simulated_charge_success:
            payment.status = PaymentStatus.SUCCESS.value
            payment.provider_payment_id = f"ch_{uuid.uuid4().hex[:16]}"
            payment.updated_at = now
            order.status = OrderStatus.PAID.value
            await self.session.commit()
            await self.session.refresh(payment)
            return True, "Payment retry succeeded", payment
        else:
            payment.status = PaymentStatus.FAILED.value
            payment.error_code = "CARD_DECLINED"
            payment.updated_at = now
            await self.session.commit()
            await self.session.refresh(payment)
            return False, "Payment retry failed: CARD_DECLINED", payment

    async def cancel_order(self, order_id: str, reason: str = "Buyer requested") -> OrderRecord:
        """
        Order cancellation with automatic held stock restoration (FLS-098).
        Validates transition via OrderStateMachine.
        """
        stmt = select(OrderRecord).where(OrderRecord.order_id == order_id)
        res = await self.session.execute(stmt)
        order = res.scalars().first()
        if not order:
            raise ValueError(f"Order '{order_id}' not found")

        # Validate legal transition
        current_st = OrderStatus(order.status)
        OrderStateMachine.validate_transition(current_st, OrderStatus.CANCELLED)

        # 1. Update order status
        order.status = OrderStatus.CANCELLED.value

        # 2. Restore held stock back to available pool
        inv_stmt = (
            update(InventoryRecord)
            .where(InventoryRecord.sku_id == order.sku_id)
            .values(
                available=InventoryRecord.available + order.quantity,
                reserved=InventoryRecord.reserved - order.quantity
            )
        )
        await self.session.execute(inv_stmt)
        await self.session.commit()
        await self.session.refresh(order)
        return order

    async def initiate_refund(
        self,
        order_id: str,
        payment_id: str,
        amount_cents: int,
        idempotency_key: str,
        reason: str = "Customer request"
    ) -> RefundRecord:
        """
        Refund initiation (FLS-099).
        Guarantees (§9 Invariant):
        - Idempotent: same idempotency key returns existing refund without double-charging
        - Refund amount <= captured payment amount
        """
        # 1. Idempotency check
        existing_stmt = select(RefundRecord).where(RefundRecord.idempotency_key == idempotency_key)
        existing_res = await self.session.execute(existing_stmt)
        existing = existing_res.scalars().first()
        if existing:
            return existing

        # 2. Payment verification
        pay_stmt = select(PaymentRecord).where(PaymentRecord.payment_id == payment_id)
        pay_res = await self.session.execute(pay_stmt)
        payment = pay_res.scalars().first()
        if not payment:
            raise ValueError(f"Payment '{payment_id}' not found")
        if payment.status != PaymentStatus.SUCCESS.value:
            raise ValueError(f"Cannot refund payment with status '{payment.status}'")

        # Invariant: refund amount never exceeds captured amount
        if amount_cents > payment.amount_cents:
            raise ValueError(
                f"Refund amount ({amount_cents} cents) cannot exceed captured payment amount ({payment.amount_cents} cents)"
            )

        # Check total existing refunds on this payment
        sum_stmt = select(func.coalesce(func.sum(RefundRecord.amount_cents), 0)).where(RefundRecord.payment_id == payment_id)
        total_refunded = (await self.session.scalar(sum_stmt)) or 0
        if total_refunded + amount_cents > payment.amount_cents:
            raise ValueError(
                f"Cumulative refund ({total_refunded + amount_cents} cents) exceeds payment amount ({payment.amount_cents} cents)"
            )

        refund_id = f"ref_{uuid.uuid4().hex[:12]}"
        refund = RefundRecord(
            refund_id=refund_id,
            payment_id=payment_id,
            order_id=order_id,
            amount_cents=amount_cents,
            idempotency_key=idempotency_key,
            status=RefundStatus.SUCCESS.value,
            reason=reason,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(refund)

        # Update order status to REFUNDED if fully refunded
        if total_refunded + amount_cents == payment.amount_cents:
            order_stmt = select(OrderRecord).where(OrderRecord.order_id == order_id)
            order_res = await self.session.execute(order_stmt)
            order = order_res.scalars().first()
            if order:
                order.status = OrderStatus.REFUNDED.value

        await self.session.commit()
        await self.session.refresh(refund)
        return refund

    async def get_refund_status(self, refund_id: str) -> Optional[Dict[str, Any]]:
        """
        Queries refund status and details (FLS-100).
        """
        stmt = select(RefundRecord).where(RefundRecord.refund_id == refund_id)
        res = await self.session.execute(stmt)
        ref = res.scalars().first()
        if not ref:
            return None
        return {
            "refund_id": ref.refund_id,
            "order_id": ref.order_id,
            "payment_id": ref.payment_id,
            "amount_cents": ref.amount_cents,
            "status": ref.status,
            "reason": ref.reason,
            "created_at": ref.created_at.isoformat() if ref.created_at else None
        }

    async def audit_inventory_to_order_consistency(self) -> List[Dict[str, Any]]:
        """
        Inventory-to-order consistency audit job (FLS-101).
        Detects drift between inventory sold counters and paid orders (§9 Invariant).
        Returns list of discrepancy records.
        """
        inv_stmt = select(InventoryRecord)
        inv_res = await self.session.execute(inv_stmt)
        inventory_items = inv_res.scalars().all()

        discrepancies: List[Dict[str, Any]] = []

        for inv in inventory_items:
            # Sum paid orders for this SKU
            order_stmt = (
                select(func.coalesce(func.sum(OrderRecord.quantity), 0))
                .where(OrderRecord.sku_id == inv.sku_id)
                .where(OrderRecord.status == OrderStatus.PAID.value)
            )
            total_paid_orders = (await self.session.scalar(order_stmt)) or 0

            # 1. Sold count consistency check
            is_sold_consistent = (inv.sold == total_paid_orders)

            # 2. Conservation invariant check
            is_conserved = (inv.available + inv.reserved + inv.sold == inv.total_allocated)

            if not is_sold_consistent or not is_conserved:
                discrepancies.append({
                    "sku_id": inv.sku_id,
                    "product_id": inv.product_id,
                    "inventory_sold": inv.sold,
                    "orders_paid": total_paid_orders,
                    "sold_drift": inv.sold - total_paid_orders,
                    "is_sold_consistent": is_sold_consistent,
                    "total_allocated": inv.total_allocated,
                    "conservation_sum": inv.available + inv.reserved + inv.sold,
                    "is_conserved": is_conserved
                })

        return discrepancies
