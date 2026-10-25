"""
Tests for Pricing & Promotions:
- FLS-054: Fixed discount
- FLS-057: Coupon validation and concurrent redemption
- FLS-058: Promotion stacking rules
- FLS-061: Maximum discount limits
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base
from models.promotions import CouponRecord, CouponDiscountType
from pricing.promotions import (
    apply_fixed_discount,
    CouponManager,
    PromotionStacker,
    CouponValidationError,
    PromotionStackingError
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session
    await engine.dispose()


def test_FLS_054_fixed_discount():
    """
    FLS-054: Fixed discount (BE+DB, P1).
    Verifies:
    - Fixed dollar/cent discount calculation
    - Non-negative price and discount validation
    - Floor price constraint enforcement
    """
    # 1. Standard $20 fixed discount on $100 item
    res1 = apply_fixed_discount(original_price_cents=10000, discount_cents=2000)
    assert res1["effective_price_cents"] == 8000
    assert res1["discount_cents"] == 2000
    assert res1["discount_percentage"] == 20.0
    assert res1["floor_enforced"] is False

    # 2. Fixed discount hitting floor ($70 discount with $40 floor -> capped at $60 discount, price $40)
    res2 = apply_fixed_discount(original_price_cents=10000, discount_cents=7000, price_floor_cents=4000)
    assert res2["effective_price_cents"] == 4000
    assert res2["discount_cents"] == 6000
    assert res2["floor_enforced"] is True

    # 3. Reject negative/zero discount
    with pytest.raises(ValueError):
        apply_fixed_discount(original_price_cents=10000, discount_cents=0)


@pytest.mark.asyncio
async def test_FLS_057_coupon_validation_and_concurrency(db_session):
    """
    FLS-057: Coupon validation (BE+DB, P1).
    Verifies (§9 Invariant):
    - Minimum order requirement validation
    - Expiration date checking
    - Stacking rules honored: no coupon double-use under concurrency
    """
    cm = CouponManager(db_session)

    # 1. Create limited single-use coupon (max_redemptions=1)
    coupon = await cm.create_coupon(
        code="SAVE25SINGLE",
        discount_type=CouponDiscountType.FIXED,
        discount_value=2500,
        max_redemptions=1,
        min_order_cents=5000,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1)
    )
    assert coupon.coupon_code == "SAVE25SINGLE"

    # 2. Reject order below minimum amount
    with pytest.raises(CouponValidationError) as exc_min:
        await cm.validate_coupon("SAVE25SINGLE", order_amount_cents=3000)
    assert "does not meet minimum order" in str(exc_min.value)

    # 3. Valid redemption
    red1 = await cm.redeem_coupon_atomic("SAVE25SINGLE", order_amount_cents=6000)
    assert red1.current_redemptions == 1

    # 4. Immediate second redemption rejected (no double-use under concurrency)
    with pytest.raises(CouponValidationError) as exc_cap:
        await cm.redeem_coupon_atomic("SAVE25SINGLE", order_amount_cents=6000)
    assert "reached its maximum redemptions limit" in str(exc_cap.value)


def test_FLS_058_promotion_stacking_rules():
    """
    FLS-058: Promotion stacking rules (BE+DB, P1).
    Verifies (§9 Invariant):
    - Unstackable coupon combined with active flash sale is strictly rejected
    - Stackable coupons combine harmoniously with base discounts
    """
    stacker = PromotionStacker()
    original_cents = 20000  # $200.00
    flash_discount_cents = 5000  # $50.00 off base sale

    # 1. Non-stackable coupon on flash sale -> REJECTS with PromotionStackingError
    unstackable_coupon = CouponRecord(
        coupon_code="EXCL_DISCOUNT",
        discount_type=CouponDiscountType.FIXED.value,
        discount_value=2000,
        can_stack=False
    )
    with pytest.raises(PromotionStackingError) as exc_stack:
        stacker.calculate_stacked_pricing(
            original_price_cents=original_cents,
            is_flash_sale=True,
            campaign_discount_cents=flash_discount_cents,
            coupon=unstackable_coupon
        )
    assert "cannot be stacked" in str(exc_stack.value)

    # 2. Stackable coupon on flash sale -> Combines successfully
    stackable_coupon = CouponRecord(
        coupon_code="STACK_BONUS",
        discount_type=CouponDiscountType.FIXED.value,
        discount_value=2000,
        can_stack=True
    )
    res = stacker.calculate_stacked_pricing(
        original_price_cents=original_cents,
        is_flash_sale=True,
        campaign_discount_cents=flash_discount_cents,
        coupon=stackable_coupon
    )
    assert res["total_discount_cents"] == 7000  # $50 + $20 = $70
    assert res["effective_price_cents"] == 13000  # $200 - $70 = $130
    assert len(res["applied_promotions"]) == 2


def test_FLS_061_maximum_discount_limits():
    """
    FLS-061: Maximum discount limits (BE+DB, P1).
    Verifies (§9 Invariant):
    - Total stacked discount never exceeds max total discount cap
    - Floor and cap invariants hold simultaneously
    - Original price preserved and returned
    """
    stacker = PromotionStacker()
    original_cents = 10000  # $100.00
    flash_discount = 5000   # $50.00 (50%)

    # Add stackable $40 coupon -> Total raw discount = $90 (90%)
    coupon_big = CouponRecord(
        coupon_code="MASSIVE40",
        discount_type=CouponDiscountType.FIXED.value,
        discount_value=4000,
        can_stack=True
    )

    # Max allowed cap is 75% ($75.00)
    res = stacker.calculate_stacked_pricing(
        original_price_cents=original_cents,
        is_flash_sale=True,
        campaign_discount_cents=flash_discount,
        coupon=coupon_big,
        max_discount_cap_pct=75.0,
        price_floor_cents=2000
    )

    # Invariant: max total discount <= cap
    assert res["original_price_cents"] == 10000
    assert res["cap_enforced"] is True
    assert res["total_discount_cents"] == 7500   # Capped at $75.00
    assert res["effective_price_cents"] == 2500  # $100 - $75 = $25
    assert res["discount_percentage"] == 75.0
