"""
Product Catalog database schema and manager (FLS-001).
Money stored in integer minor units (cents).
"""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import Column, String, BigInteger, DateTime, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, ConfigDict
from db.database import Base

class ProductRecord(Base):
    __tablename__ = "products"

    product_id = Column(String(64), primary_key=True, index=True)
    title = Column(String(256), nullable=False)
    description = Column(String(1024), default="", nullable=False)
    original_price_cents = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self):
        return {
            "product_id": self.product_id,
            "title": self.title,
            "description": self.description,
            "original_price_cents": self.original_price_cents,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }

class ProductSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    title: str
    description: str = ""
    original_price_cents: int

class ProductManager:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_product(self, schema: ProductSchema) -> ProductSchema:
        if not schema.title.strip():
            raise ValueError("Product title cannot be empty")
        if schema.original_price_cents < 0:
            raise ValueError("Price in cents cannot be negative")

        record = ProductRecord(
            product_id=schema.product_id,
            title=schema.title,
            description=schema.description,
            original_price_cents=schema.original_price_cents
        )
        self.session.add(record)
        await self.session.commit()
        return ProductSchema.model_validate(record)

    async def get_product(self, product_id: str) -> Optional[ProductSchema]:
        stmt = select(ProductRecord).where(ProductRecord.product_id == product_id)
        res = await self.session.execute(stmt)
        record = res.scalar_one_or_none()
        if not record:
            return None
        return ProductSchema.model_validate(record)

    async def list_products(self) -> List[ProductSchema]:
        stmt = select(ProductRecord)
        res = await self.session.execute(stmt)
        records = res.scalars().all()
        return [ProductSchema.model_validate(r) for r in records]
