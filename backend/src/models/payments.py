"""
Payment records database schema and manager with idempotency protection (FLS-005).
Money in integer cents.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, String, BigInteger, DateTime, CheckConstraint, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from db.database import Base

class PaymentStatus(str, Enum):
    INITIATED = "INITIATED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"

class PaymentRecord(Base):
    __tablename__ = "payments"

    payment_id = Column(String(64), primary_key=True, index=True)
    order_id = Column(String(64), ForeignKey("orders.order_id"), nullable=False, index=True)
    payment_provider = Column(String(64), nullable=False)
    provider_payment_id = Column(String(128), nullable=True)
    amount_cents = Column(BigInteger, nullable=False)
    status = Column(String(32), default=PaymentStatus.INITIATED.value, nullable=False)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    error_code = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="chk_payment_amount_nonneg"),
    )

class PaymentSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    payment_id: str
    order_id: str
    payment_provider: str
    amount_cents: int
    status: str = PaymentStatus.INITIATED.value
    idempotency_key: str
    provider_payment_id: Optional[str] = None
    error_code: Optional[str] = None

class PaymentManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def record_payment(
        self,
        payment_id: str,
        order_id: str,
        payment_provider: str,
        amount_cents: int,
        idempotency_key: str,
        status: PaymentStatus = PaymentStatus.INITIATED,
        provider_payment_id: Optional[str] = None
    ) -> PaymentSchema:
        if amount_cents < 0:
            raise ValueError("Payment amount cannot be negative")

        stmt = select(PaymentRecord).where(PaymentRecord.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        existing = res.scalar_one_or_none()
        if existing:
            return PaymentSchema.model_validate(existing)

        now = datetime.now(timezone.utc)
        rec = PaymentRecord(
            payment_id=payment_id,
            order_id=order_id,
            payment_provider=payment_provider,
            provider_payment_id=provider_payment_id,
            amount_cents=amount_cents,
            status=status.value,
            idempotency_key=idempotency_key,
            created_at=now,
            updated_at=now
        )
        self.session.add(rec)
        await self.session.commit()
        return PaymentSchema.model_validate(rec)

    async def get_payment(self, payment_id: str) -> Optional[PaymentSchema]:
        stmt = select(PaymentRecord).where(PaymentRecord.payment_id == payment_id)
        res = await self.session.execute(stmt)
        rec = res.scalar_one_or_none()
        if not rec:
            return None
        return PaymentSchema.model_validate(rec)

    async def get_payment_by_idempotency(self, idempotency_key: str) -> Optional[PaymentSchema]:
        stmt = select(PaymentRecord).where(PaymentRecord.idempotency_key == idempotency_key)
        res = await self.session.execute(stmt)
        rec = res.scalar_one_or_none()
        if not rec:
            return None
        return PaymentSchema.model_validate(rec)

    async def confirm_payment(
        self,
        payment_id: str,
        provider_payment_id: str
    ) -> PaymentSchema:
        """
        Transitions payment status from INITIATED to SUCCESS (FLS-093).
        Also transitions associated Order to PAID if order is still PENDING.
        """
        stmt = select(PaymentRecord).where(PaymentRecord.payment_id == payment_id)
        res = await self.session.execute(stmt)
        rec = res.scalar_one_or_none()
        if not rec:
            raise ValueError(f"Payment '{payment_id}' not found")

        if rec.status == PaymentStatus.SUCCESS.value:
            return PaymentSchema.model_validate(rec)

        if rec.status != PaymentStatus.INITIATED.value:
            raise ValueError(f"Cannot confirm payment with status '{rec.status}'")

        rec.status = PaymentStatus.SUCCESS.value
        rec.provider_payment_id = provider_payment_id
        rec.updated_at = datetime.now(timezone.utc)

        # Update order status to PAID
        from models.orders import OrderRecord, OrderStatus
        order_stmt = select(OrderRecord).where(OrderRecord.order_id == rec.order_id)
        order_res = await self.session.execute(order_stmt)
        order_rec = order_res.scalar_one_or_none()
        if order_rec and order_rec.status == OrderStatus.PENDING.value:
            order_rec.status = OrderStatus.PAID.value

        await self.session.commit()
        return PaymentSchema.model_validate(rec)


class RefundStatus(str, Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class RefundRecord(Base):
    __tablename__ = "refunds"

    refund_id = Column(String(64), primary_key=True, index=True)
    payment_id = Column(String(64), ForeignKey("payments.payment_id"), nullable=False, index=True)
    order_id = Column(String(64), ForeignKey("orders.order_id"), nullable=False, index=True)
    amount_cents = Column(BigInteger, nullable=False)
    idempotency_key = Column(String(128), unique=True, nullable=False, index=True)
    status = Column(String(32), default=RefundStatus.PENDING.value, nullable=False)
    reason = Column(String(256), default="", nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="chk_refund_amount_positive"),
    )


