"""
Sale-Specific Pricing Engine (FLS-019).
Resolves dynamic flash sale discount prices while preserving original price baseline.
"""

from typing import Optional, Dict, Any
from datetime import datetime, timezone
from models.catalog import ProductSchema
from models.campaigns import CampaignSchema, CampaignStatus

class PricingEngine:
    """
    Computes effective pricing based on product baseline and active campaign conditions.
    """
    def resolve_price(
        self,
        product: ProductSchema,
        campaign: Optional[CampaignSchema] = None,
        now: Optional[datetime] = None
    ) -> Dict[str, Any]:
        current_time = now or datetime.now(timezone.utc)
        original_cents = product.original_price_cents

        if campaign is not None and campaign.status == CampaignStatus.ACTIVE.value:
            # Verify campaign time bounds
            if campaign.start_time <= current_time <= campaign.end_time:
                sale_cents = campaign.sale_price_cents
                discount_cents = max(0, original_cents - sale_cents)
                return {
                    "is_flash_sale": True,
                    "campaign_id": campaign.campaign_id,
                    "effective_price_cents": sale_cents,
                    "original_price_cents": original_cents,
                    "discount_cents": discount_cents,
                    "currency": "USD_CENTS"
                }

        # Fallback to standard catalog price
        return {
            "is_flash_sale": False,
            "campaign_id": None,
            "effective_price_cents": original_cents,
            "original_price_cents": original_cents,
            "discount_cents": 0,
            "currency": "USD_CENTS"
        }

    def apply_percentage_discount(
        self,
        original_price_cents: int,
        discount_percentage: float,
        price_floor_cents: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Computes percentage-based promotional discount in exact integer cents (FLS-053).
        Validates discount percentage bounds [0, 100].
        Respects price floor validation (FLS-062).
        """
        if original_price_cents < 0:
            raise ValueError("Original price cannot be negative")
        if not (0.0 <= discount_percentage <= 100.0):
            raise ValueError(f"Discount percentage {discount_percentage} must be between 0 and 100")

        # Deterministic rounding to nearest cent
        discount_cents = round(original_price_cents * (discount_percentage / 100.0))
        computed_price = original_price_cents - discount_cents

        floor_enforced = False
        if price_floor_cents is not None:
            if price_floor_cents < 0:
                raise ValueError("Price floor cannot be negative")
            if price_floor_cents > original_price_cents:
                raise ValueError("Price floor cannot exceed original price")
            if computed_price < price_floor_cents:
                computed_price = price_floor_cents
                discount_cents = original_price_cents - computed_price
                floor_enforced = True

        return {
            "original_price_cents": original_price_cents,
            "discount_percentage": discount_percentage,
            "discount_cents": discount_cents,
            "effective_price_cents": computed_price,
            "price_floor_cents": price_floor_cents,
            "floor_enforced": floor_enforced,
            "currency": "USD_CENTS"
        }

    def validate_price_floor(
        self,
        sale_price_cents: int,
        price_floor_cents: int
    ) -> bool:
        """
        Validates whether a sale price satisfies the minimum allowable price floor (FLS-062).
        """
        if price_floor_cents < 0:
            raise ValueError("Price floor cannot be negative")
        return sale_price_cents >= price_floor_cents

