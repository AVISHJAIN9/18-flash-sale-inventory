"""
Promotion Engine, Coupon Validation, and Stacking Rules (FLS-054, FLS-057, FLS-058, FLS-061).
Enforces:
- Fixed discount computation with floor and cap preservation (FLS-054)
- Coupon validation and atomic redemption preventing double-use under concurrency (FLS-057)
- Promotion stacking rules rejecting unstackable combinations (FLS-058)
- Maximum total discount limit capping (FLS-061)
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.promotions import CouponRecord, CouponDiscountType


class PromotionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CouponValidationError(PromotionError):
    def __init__(self, message: str):
        super().__init__("COUPON_INVALID", message)


class PromotionStackingError(PromotionError):
    def __init__(self, message: str):
        super().__init__("PROMOTION_STACKING_VIOLATION", message)


def apply_fixed_discount(
    original_price_cents: int,
    discount_cents: int,
    price_floor_cents: Optional[int] = None,
    max_discount_cap_pct: float = 90.0
) -> Dict[str, Any]:
    """
    Applies fixed dollar/cent discount to product baseline (FLS-054).
    Validates non-negative values, ensures price >= floor, and discount <= cap.
    """
    if original_price_cents <= 0:
        raise ValueError("Original price must be positive")
    if discount_cents <= 0:
        raise ValueError("Fixed discount must be strictly positive")

    # Raw computation
    computed_price = original_price_cents - discount_cents
    effective_discount = discount_cents

    # Floor enforcement
    floor_enforced = False
    effective_floor = price_floor_cents or 0
    if computed_price < effective_floor:
        computed_price = effective_floor
        effective_discount = original_price_cents - computed_price
        floor_enforced = True

    # Max discount cap enforcement (FLS-061)
    cap_enforced = False
    max_allowed_discount = round(original_price_cents * (max_discount_cap_pct / 100.0))
    if effective_discount > max_allowed_discount:
        effective_discount = max_allowed_discount
        computed_price = original_price_cents - effective_discount
        cap_enforced = True

    discount_pct = (effective_discount / original_price_cents) * 100.0

    return {
        "original_price_cents": original_price_cents,
        "discount_cents": effective_discount,
        "effective_price_cents": computed_price,
        "discount_percentage": round(discount_pct, 2),
        "price_floor_cents": price_floor_cents,
        "floor_enforced": floor_enforced,
        "cap_enforced": cap_enforced,
        "currency": "USD"
    }


class CouponManager:
    """
    Coupon validation and atomic redemption service (FLS-057).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_coupon(
        self,
        code: str,
        discount_type: CouponDiscountType,
        discount_value: int,
        max_redemptions: int = 100,
        can_stack: bool = False,
        min_order_cents: int = 0,
        expires_at: Optional[datetime] = None
    ) -> CouponRecord:
        coupon = CouponRecord(
            coupon_code=code.strip().upper(),
            discount_type=discount_type.value,
            discount_value=discount_value,
            max_redemptions=max_redemptions,
            current_redemptions=0,
            can_stack=can_stack,
            min_order_cents=min_order_cents,
            is_active=True,
            expires_at=expires_at
        )
        self.session.add(coupon)
        await self.session.commit()
        await self.session.refresh(coupon)
        return coupon

    async def validate_coupon(
        self,
        code: str,
        order_amount_cents: int,
        now: Optional[datetime] = None
    ) -> CouponRecord:
        stmt = select(CouponRecord).where(CouponRecord.coupon_code == code.strip().upper())
        res = await self.session.execute(stmt)
        coupon = res.scalars().first()

        if not coupon:
            raise CouponValidationError(f"Coupon code '{code}' does not exist")
        if not coupon.is_active:
            raise CouponValidationError(f"Coupon '{code}' is deactivated")
        if coupon.current_redemptions >= coupon.max_redemptions:
            raise CouponValidationError(f"Coupon '{code}' has reached its maximum redemptions limit ({coupon.max_redemptions})")
        if order_amount_cents < coupon.min_order_cents:
            raise CouponValidationError(f"Order amount ({order_amount_cents} cents) does not meet minimum order of {coupon.min_order_cents} cents")

        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        if coupon.expires_at:
            exp = coupon.expires_at
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if current_time >= exp:
                raise CouponValidationError(f"Coupon '{code}' has expired")

        return coupon

    async def redeem_coupon_atomic(
        self,
        code: str,
        order_amount_cents: int,
        now: Optional[datetime] = None
    ) -> CouponRecord:
        """
        Atomically validates and increments redemptions preventing double-use under concurrency (§9 Invariant).
        """
        # Validate criteria first
        coupon = await self.validate_coupon(code, order_amount_cents, now=now)

        # Atomic conditional increment
        stmt = (
            update(CouponRecord)
            .where(
                CouponRecord.coupon_code == coupon.coupon_code,
                CouponRecord.current_redemptions < CouponRecord.max_redemptions
            )
            .values(current_redemptions=CouponRecord.current_redemptions + 1)
        )
        res = await self.session.execute(stmt)
        await self.session.commit()

        if res.rowcount != 1:
            raise CouponValidationError(f"Coupon '{code}' redemption exhausted under concurrency")

        await self.session.refresh(coupon)
        return coupon


class PromotionStacker:
    """
    Evaluates stacking rules between promotions, flash sale campaigns, and coupons (FLS-058, FLS-061).
    """

    @staticmethod
    def calculate_stacked_pricing(
        original_price_cents: int,
        is_flash_sale: bool,
        campaign_discount_cents: int = 0,
        coupon: Optional[CouponRecord] = None,
        price_floor_cents: Optional[int] = None,
        max_discount_cap_pct: float = 85.0
    ) -> Dict[str, Any]:
        """
        Calculates combined discount and enforces stacking rules (§9 Invariant):
        - Stacking rules honored: if coupon.can_stack is False and is_flash_sale is True -> rejects stacking!
        - Total combined discount <= max_discount_cap_pct
        - Sale price >= price_floor_cents
        - Original price preserved and returned
        """
        if original_price_cents <= 0:
            raise ValueError("Original price must be positive")

        total_discount_cents = 0
        applied_promotions: List[str] = []

        # 1. Base campaign discount
        if is_flash_sale:
            total_discount_cents += campaign_discount_cents
            applied_promotions.append("FLASH_SALE_CAMPAIGN")

        # 2. Coupon evaluation
        if coupon is not None:
            if is_flash_sale and not coupon.can_stack:
                raise PromotionStackingError(
                    f"Coupon '{coupon.coupon_code}' cannot be stacked with active flash sale discounts"
                )

            # Compute coupon savings
            if coupon.discount_type == CouponDiscountType.FIXED.value:
                coupon_savings = coupon.discount_value
            else:
                # Percentage of price after campaign or original
                base_for_pct = original_price_cents - total_discount_cents
                coupon_savings = round(base_for_pct * (coupon.discount_value / 100.0))

            total_discount_cents += coupon_savings
            applied_promotions.append(f"COUPON:{coupon.coupon_code}")

        # 3. Maximum total discount limit capping (FLS-061)
        max_total_discount_allowed = round(original_price_cents * (max_discount_cap_pct / 100.0))
        cap_enforced = False
        if total_discount_cents > max_total_discount_allowed:
            total_discount_cents = max_total_discount_allowed
            cap_enforced = True

        # 4. Price floor enforcement
        floor = price_floor_cents or 0
        floor_enforced = False
        computed_price = original_price_cents - total_discount_cents
        if computed_price < floor:
            computed_price = floor
            total_discount_cents = original_price_cents - computed_price
            floor_enforced = True

        effective_pct = (total_discount_cents / original_price_cents) * 100.0

        return {
            "original_price_cents": original_price_cents,
            "total_discount_cents": total_discount_cents,
            "effective_price_cents": computed_price,
            "discount_percentage": round(effective_pct, 2),
            "applied_promotions": applied_promotions,
            "cap_enforced": cap_enforced,
            "floor_enforced": floor_enforced,
            "price_floor_cents": price_floor_cents,
            "currency": "USD"
        }
