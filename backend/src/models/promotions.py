"""
Promotion and Coupon database schema (FLS-054, FLS-057, FLS-058, FLS-061).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from sqlalchemy import Column, String, BigInteger, Integer, Boolean, DateTime, CheckConstraint, select
from db.database import Base


class CouponDiscountType(str, Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED = "FIXED"


class CouponRecord(Base):
    __tablename__ = "coupons"

    coupon_code = Column(String(64), primary_key=True, index=True)
    description = Column(String(256), default="", nullable=False)
    discount_type = Column(String(32), default=CouponDiscountType.FIXED.value, nullable=False)
    discount_value = Column(BigInteger, nullable=False)  # cents for FIXED, percentage points for PERCENTAGE
    min_order_cents = Column(BigInteger, default=0, nullable=False)
    max_redemptions = Column(Integer, default=100, nullable=False)
    current_redemptions = Column(Integer, default=0, nullable=False)
    can_stack = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        CheckConstraint("current_redemptions <= max_redemptions", name="chk_coupon_redemption_cap"),
        CheckConstraint("discount_value > 0", name="chk_coupon_discount_positive"),
        CheckConstraint("min_order_cents >= 0", name="chk_coupon_min_order_nonneg"),
    )
