"""
Atomic Checkout and Purchase Flow Service (FLS-067, FLS-069, FLS-070, FLS-071, FLS-075, FLS-076).
Enforces:
- Idempotency keys (FLS-070) & duplicate-order prevention (FLS-071)
- Per-user purchase limit (FLS-067)
- Reservation token verification (FLS-075) & checkout timeout (FLS-076)
- Atomic multi-table transition: reservation -> confirmed, inventory -> sold, order & payment persisted.
"""

from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import uuid
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.inventory import InventoryRecord, ReservationRecord, ReservationStatus
from models.orders import OrderRecord, OrderStatus, OrderSchema
from models.payments import PaymentRecord, PaymentStatus
from models.catalog import ProductRecord
from clock import Clock

class CheckoutService:
    def __init__(self, session: AsyncSession, clock: Optional[Clock] = None):
        self.session = session
        self.clock = clock or Clock()

    async def get_user_purchased_quantity(self, user_id: str, sku_id: str) -> int:
        """
        Calculates cumulative items purchased or pending by user for this SKU (FLS-067).
        """
        # Sum quantities in confirmed/paid orders
        order_stmt = (
            select(func.coalesce(func.sum(OrderRecord.quantity), 0))
            .where(OrderRecord.user_id == user_id)
            .where(OrderRecord.sku_id == sku_id)
            .where(OrderRecord.status.in_([OrderStatus.PENDING.value, OrderStatus.PAID.value]))
        )
        total_orders = await self.session.scalar(order_stmt) or 0
        return total_orders

    async def process_checkout(
        self,
        user_id: str,
        sku_id: str,
        quantity: int,
        unit_price_cents: int,
        reservation_token: str,
        idempotency_key: str,
        max_quantity_per_user: Optional[int] = None,
        payment_provider: str = "stripe_flash_gateway"
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Executes atomic checkout (FLS-069).
        Guarantees single execution via idempotency key (FLS-070, FLS-071).
        Enforces per-user purchase limits (FLS-067) and reservation validity (FLS-075, FLS-076).
        """
        if quantity <= 0:
            return False, "Quantity must be positive", None

        # 1. Idempotency Check (FLS-070, FLS-071)
        existing_order_stmt = select(OrderRecord).where(OrderRecord.idempotency_key == idempotency_key)
        res_existing = await self.session.execute(existing_order_stmt)
        existing_order = res_existing.scalar_one_or_none()
        if existing_order:
            return True, "Order already processed (idempotent replay)", {
                "order_id": existing_order.order_id,
                "user_id": existing_order.user_id,
                "sku_id": existing_order.sku_id,
                "quantity": existing_order.quantity,
                "total_amount_cents": existing_order.total_amount_cents,
                "idempotency_key": existing_order.idempotency_key,
                "status": existing_order.status,
                "is_replay": True
            }

        # 2. Per-User Purchase Limit (FLS-067)
        if max_quantity_per_user is not None:
            prior_qty = await self.get_user_purchased_quantity(user_id, sku_id)
            if prior_qty + quantity > max_quantity_per_user:
                return False, f"Purchase limit exceeded: user has {prior_qty}, cannot purchase {quantity} (max: {max_quantity_per_user})", None

        now_ts = self.clock.now()
        now_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc)

        # 3. Reservation Token Verification (FLS-075) & Timeout Check (FLS-076)
        res_stmt = select(ReservationRecord).where(ReservationRecord.reservation_id == reservation_token)
        res_match = await self.session.execute(res_stmt)
        reservation = res_match.scalar_one_or_none()

        if not reservation:
            return False, f"Reservation token '{reservation_token}' not found", None

        if reservation.user_id != user_id:
            return False, "Reservation token belongs to a different user", None

        if reservation.sku_id != sku_id:
            return False, "Reservation token SKU mismatch", None

        if reservation.status != ReservationStatus.PENDING.value:
            return False, f"Cannot checkout reservation with status '{reservation.status}'", None

        expires_at = reservation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)

        if expires_at <= now_dt:
            # Mark expired and return stock
            reservation.status = ReservationStatus.EXPIRED.value
            restore_inv = (
                update(InventoryRecord)
                .where(InventoryRecord.sku_id == sku_id)
                .values(
                    available=InventoryRecord.available + reservation.quantity,
                    reserved=InventoryRecord.reserved - reservation.quantity,
                    updated_at=datetime.now(timezone.utc)
                )
            )
            await self.session.execute(restore_inv)
            await self.session.commit()
            return False, "Reservation has expired (checkout timeout)", None

        if reservation.quantity < quantity:
            return False, f"Reservation quantity ({reservation.quantity}) is less than checkout quantity ({quantity})", None

        # 4. Atomic Multi-Table Update
        # Transition reservation status
        reservation.status = ReservationStatus.CONFIRMED.value

        # Transition inventory from reserved to sold
        inv_stmt = (
            update(InventoryRecord)
            .where(InventoryRecord.sku_id == sku_id)
            .where(InventoryRecord.reserved >= quantity)
            .values(
                reserved=InventoryRecord.reserved - quantity,
                sold=InventoryRecord.sold + quantity,
                updated_at=datetime.now(timezone.utc)
            )
        )
        inv_res = await self.session.execute(inv_stmt)
        if inv_res.rowcount == 0:
            await self.session.rollback()
            return False, "Inventory reservation update failed", None

        total_amount_cents = quantity * unit_price_cents
        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"

        # Create Order Record
        order = OrderRecord(
            order_id=order_id,
            user_id=user_id,
            sku_id=sku_id,
            quantity=quantity,
            unit_price_cents=unit_price_cents,
            total_amount_cents=total_amount_cents,
            idempotency_key=idempotency_key,
            status=OrderStatus.PAID.value
        )
        self.session.add(order)

        # Create Payment Record
        payment = PaymentRecord(
            payment_id=payment_id,
            order_id=order_id,
            payment_provider=payment_provider,
            provider_payment_id=f"prov_{uuid.uuid4().hex[:16]}",
            amount_cents=total_amount_cents,
            idempotency_key=f"pay_idem_{idempotency_key}",
            status=PaymentStatus.SUCCESS.value
        )
        self.session.add(payment)

        # Commit all atomically
        await self.session.commit()

        return True, "Checkout completed successfully", {
            "order_id": order_id,
            "payment_id": payment_id,
            "user_id": user_id,
            "sku_id": sku_id,
            "quantity": quantity,
            "total_amount_cents": total_amount_cents,
            "idempotency_key": idempotency_key,
            "status": OrderStatus.PAID.value,
            "is_replay": False
        }
