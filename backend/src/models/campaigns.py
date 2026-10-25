"""
Flash sale campaign database schema and manager (FLS-006).
Money in integer cents.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from sqlalchemy import Column, String, BigInteger, Integer, DateTime, ForeignKey, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from db.database import Base

class CampaignStatus(str, Enum):
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"

class CampaignRecord(Base):
    __tablename__ = "campaigns"

    campaign_id = Column(String(64), primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    sku_id = Column(String(64), ForeignKey("inventory.sku_id"), nullable=False, index=True)
    start_time = Column(DateTime(timezone=True), nullable=False)
    end_time = Column(DateTime(timezone=True), nullable=False)
    sale_price_cents = Column(BigInteger, nullable=False)
    allocated_stock = Column(BigInteger, nullable=False)
    per_user_limit = Column(Integer, default=1, nullable=False)
    status = Column(String(32), default=CampaignStatus.SCHEDULED.value, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

class CampaignSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    campaign_id: str
    title: str
    sku_id: str
    start_time: datetime
    end_time: datetime
    sale_price_cents: int
    allocated_stock: int
    per_user_limit: int = 1
    status: str = CampaignStatus.SCHEDULED.value

class CampaignManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_campaign(self, schema: CampaignSchema) -> CampaignSchema:
        if schema.end_time <= schema.start_time:
            raise ValueError("end_time must be strictly after start_time")
        if schema.sale_price_cents < 0:
            raise ValueError("sale_price_cents cannot be negative")
        if schema.allocated_stock <= 0:
            raise ValueError("allocated_stock must be > 0")

        rec = CampaignRecord(
            campaign_id=schema.campaign_id,
            title=schema.title,
            sku_id=schema.sku_id,
            start_time=schema.start_time,
            end_time=schema.end_time,
            sale_price_cents=schema.sale_price_cents,
            allocated_stock=schema.allocated_stock,
            per_user_limit=schema.per_user_limit,
            status=schema.status,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(rec)
        await self.session.commit()
        return CampaignSchema.model_validate(rec)

    async def get_campaign(self, campaign_id: str) -> Optional[CampaignSchema]:
        stmt = select(CampaignRecord).where(CampaignRecord.campaign_id == campaign_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return CampaignSchema.model_validate(record)

    async def list_campaigns(self) -> List[CampaignSchema]:
        stmt = select(CampaignRecord)
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [CampaignSchema.model_validate(r) for r in records]
