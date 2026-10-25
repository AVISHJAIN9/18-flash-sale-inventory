"""
Order database schema and manager with idempotency protection (FLS-004).
Money stored in integer cents.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, String, BigInteger, Integer, DateTime, CheckConstraint, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from db.database import Base

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"
    EXPIRED = "EXPIRED"

class OrderStateMachine:
    """
    Formal deterministic state machine for Order lifecycle (FLS-091).
    Validates legal transitions:
    - PENDING -> PAID, CANCELLED, EXPIRED
    - PAID -> REFUNDED
    - Terminal states (CANCELLED, REFUNDED, EXPIRED) cannot transition.
    """
    VALID_TRANSITIONS = {
        OrderStatus.PENDING: {OrderStatus.PAID, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
        OrderStatus.PAID: {OrderStatus.REFUNDED},
        OrderStatus.CANCELLED: set(),
        OrderStatus.REFUNDED: set(),
        OrderStatus.EXPIRED: set()
    }

    @classmethod
    def can_transition(cls, current: OrderStatus, target: OrderStatus) -> bool:
        return target in cls.VALID_TRANSITIONS.get(current, set())

    @classmethod
    def validate_transition(cls, current: OrderStatus, target: OrderStatus) -> None:
        if not cls.can_transition(current, target):
            raise ValueError(f"Illegal order state transition from '{current.value}' to '{target.value}'")


class OrderRecord(Base):
    __tablename__ = "orders"

    order_id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    sku_id = Column(String(64), ForeignKey("inventory.sku_id"), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_price_cents = Column(BigInteger, nullable=False)
    total_amount_cents = Column(BigInteger, nullable=False)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    status = Column(String(32), default=OrderStatus.PENDING.value, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_order_qty_positive"),
        CheckConstraint("total_amount_cents >= 0", name="chk_order_amount_nonneg"),
    )

class OrderSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    user_id: str
    sku_id: str
    quantity: int
    unit_price_cents: int
    total_amount_cents: int
    idempotency_key: str
    status: str = OrderStatus.PENDING.value

class OrderManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_order(
        self,
        order_id: str,
        user_id: str,
        sku_id: str,
        quantity: int,
        unit_price_cents: int,
        idempotency_key: str
    ) -> OrderSchema:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")
        if unit_price_cents < 0:
            raise ValueError("Unit price cannot be negative")

        # Idempotency check: if order with this idempotency_key already exists, return it
        stmt = select(OrderRecord).where(OrderRecord.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return OrderSchema.model_validate(existing)

        total_cents = quantity * unit_price_cents
        rec = OrderRecord(
            order_id=order_id,
            user_id=user_id,
            sku_id=sku_id,
            quantity=quantity,
            unit_price_cents=unit_price_cents,
            total_amount_cents=total_cents,
            idempotency_key=idempotency_key,
            status=OrderStatus.PENDING.value,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(rec)
        await self.session.commit()
        return OrderSchema.model_validate(rec)

    async def get_order(self, order_id: str) -> Optional[OrderSchema]:
        stmt = select(OrderRecord).where(OrderRecord.order_id == order_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return OrderSchema.model_validate(record)

    async def list_orders_by_user(self, user_id: str) -> List[OrderSchema]:
        stmt = select(OrderRecord).where(OrderRecord.user_id == user_id)
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [OrderSchema.model_validate(r) for r in records]

    async def transition_order_status(self, order_id: str, new_status: OrderStatus) -> OrderSchema:
        """
        Transitions order status adhering strictly to OrderStateMachine (FLS-091).
        """
        stmt = select(OrderRecord).where(OrderRecord.order_id == order_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            raise ValueError(f"Order '{order_id}' not found")

        current = OrderStatus(record.status)
        OrderStateMachine.validate_transition(current, new_status)

        record.status = new_status.value
        await self.session.commit()
        return OrderSchema.model_validate(record)

    async def expire_stale_orders(
        self,
        timeout_seconds: int = 900,
        current_time: Optional[datetime] = None
    ) -> List[str]:
        """
        Scans for PENDING orders created more than timeout_seconds ago and transitions to EXPIRED (FLS-097).
        """
        from datetime import timedelta
        now = current_time or datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=timeout_seconds)

        stmt = select(OrderRecord).where(OrderRecord.status == OrderStatus.PENDING.value)
        res = await self.session.execute(stmt)
        pending_orders = res.scalars().all()

        expired_ids = []
        for order in pending_orders:
            created = order.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if created <= cutoff:
                order.status = OrderStatus.EXPIRED.value
                expired_ids.append(order.order_id)

        await self.session.commit()
        return expired_ids


