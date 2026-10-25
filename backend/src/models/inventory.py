"""
Inventory database schema and Reservation store (FLS-002, FLS-003).
Enforces core conservation invariant: available + reserved + sold == total_allocated and non-negative stock.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, String, BigInteger, Integer, DateTime, CheckConstraint, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from db.database import Base

class ReservationStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    RELEASED = "RELEASED"

class InventoryRecord(Base):
    __tablename__ = "inventory"

    sku_id = Column(String(64), primary_key=True, index=True)
    product_id = Column(String(64), ForeignKey("products.product_id"), nullable=False, index=True)
    total_allocated = Column(BigInteger, nullable=False)
    available = Column(BigInteger, nullable=False)
    reserved = Column(BigInteger, default=0, nullable=False)
    sold = Column(BigInteger, default=0, nullable=False)
    version = Column(BigInteger, default=1, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("available >= 0", name="chk_inventory_available_nonneg"),
        CheckConstraint("reserved >= 0", name="chk_inventory_reserved_nonneg"),
        CheckConstraint("sold >= 0", name="chk_inventory_sold_nonneg"),
        CheckConstraint("available + reserved + sold == total_allocated", name="chk_inventory_conservation"),
    )

class ReservationRecord(Base):
    __tablename__ = "reservations"

    reservation_id = Column(String(64), primary_key=True, index=True)
    sku_id = Column(String(64), ForeignKey("inventory.sku_id"), nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(32), default=ReservationStatus.PENDING.value, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("quantity > 0", name="chk_reservation_qty_positive"),
    )

class InventorySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    sku_id: str
    product_id: str
    total_allocated: int
    available: int
    reserved: int = 0
    sold: int = 0

class ReservationSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    reservation_id: str
    sku_id: str
    user_id: str
    quantity: int
    status: str = ReservationStatus.PENDING.value
    expires_at: datetime

class InventoryManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def initialize_inventory(self, sku_id: str, product_id: str, total_allocated: int) -> InventorySchema:
        if total_allocated <= 0:
            raise ValueError("total_allocated must be > 0")

        record = InventoryRecord(
            sku_id=sku_id,
            product_id=product_id,
            total_allocated=total_allocated,
            available=total_allocated,
            reserved=0,
            sold=0,
            updated_at=datetime.now(timezone.utc)
        )
        self.session.add(record)
        await self.session.commit()
        return InventorySchema.model_validate(record)

    async def get_inventory(self, sku_id: str) -> Optional[InventorySchema]:
        stmt = select(InventoryRecord).where(InventoryRecord.sku_id == sku_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return InventorySchema.model_validate(record)

    async def list_inventory(self) -> List[InventorySchema]:
        stmt = select(InventoryRecord)
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [InventorySchema.model_validate(r) for r in records]

class ReservationStore:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_reservation(
        self,
        reservation_id: str,
        sku_id: str,
        user_id: str,
        quantity: int,
        expires_at: datetime
    ) -> ReservationSchema:
        if quantity <= 0:
            raise ValueError("Quantity must be positive")

        rec = ReservationRecord(
            reservation_id=reservation_id,
            sku_id=sku_id,
            user_id=user_id,
            quantity=quantity,
            status=ReservationStatus.PENDING.value,
            expires_at=expires_at,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(rec)
        await self.session.commit()
        return ReservationSchema.model_validate(rec)

    async def get_reservation(self, reservation_id: str) -> Optional[ReservationSchema]:
        stmt = select(ReservationRecord).where(ReservationRecord.reservation_id == reservation_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return ReservationSchema.model_validate(record)

    async def list_user_reservations(self, user_id: str) -> List[ReservationSchema]:
        stmt = select(ReservationRecord).where(ReservationRecord.user_id == user_id)
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [ReservationSchema.model_validate(r) for r in records]
