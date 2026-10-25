"""
Price Validation and Original-Price Preservation Engine (FLS-020, FLS-021).
Enforces:
1. Original price preservation: Baseline catalog price is immutable and returned in all responses.
2. Sale price validation: sale_price >= price_floor, discount <= max_discount_cap, sale_price <= original_price.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict, Field


class PricingValidationError(Exception):
    """Base exception for pricing validation failures."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class InvalidSalePriceError(PricingValidationError):
    def __init__(self, message: str):
        super().__init__("INVALID_SALE_PRICE", message)


class SalePriceBelowFloorError(PricingValidationError):
    def __init__(self, message: str, floor_cents: int, offered_cents: int):
        super().__init__(
            "SALE_PRICE_BELOW_FLOOR",
            f"{message}: offered price {offered_cents} cents is below minimum floor {floor_cents} cents"
        )
        self.floor_cents = floor_cents
        self.offered_cents = offered_cents


class SaleDiscountCapExceededError(PricingValidationError):
    def __init__(self, message: str, max_cap_pct: float, calculated_pct: float):
        super().__init__(
            "DISCOUNT_CAP_EXCEEDED",
            f"{message}: calculated discount {calculated_pct:.2f}% exceeds maximum allowed cap {max_cap_pct:.2f}%"
        )
        self.max_cap_pct = max_cap_pct
        self.calculated_pct = calculated_pct


class PreservedPriceQuote(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    sku_id: Optional[str] = None
    original_price_cents: int
    sale_price_cents: int
    discount_cents: int
    discount_percentage: float
    price_floor_cents: Optional[int] = None
    max_discount_cap_pct: Optional[float] = None
    currency: str = "USD"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "product_id": self.product_id,
            "sku_id": self.sku_id,
            "original_price_cents": self.original_price_cents,
            "sale_price_cents": self.sale_price_cents,
            "discount_cents": self.discount_cents,
            "discount_percentage": self.discount_percentage,
            "price_floor_cents": self.price_floor_cents,
            "max_discount_cap_pct": self.max_discount_cap_pct,
            "currency": self.currency,
        }


class SalePriceValidator:
    """
    Validates flash sale prices against business invariants and returns preserved quotes.
    """

    def validate_and_quote(
        self,
        product_id: str,
        original_price_cents: int,
        sale_price_cents: int,
        sku_id: Optional[str] = None,
        price_floor_cents: Optional[int] = None,
        max_discount_cap_pct: float = 90.0,
        currency: str = "USD"
    ) -> PreservedPriceQuote:
        """
        Validates sale price according to §9 Invariants:
        - sale-price >= floor
        - max total discount <= cap
        - original price preserved and returned
        """
        if original_price_cents <= 0:
            raise InvalidSalePriceError(f"Original price must be positive, got {original_price_cents} cents")

        if sale_price_cents <= 0:
            raise InvalidSalePriceError(f"Sale price must be strictly positive, got {sale_price_cents} cents")

        if sale_price_cents > original_price_cents:
            raise InvalidSalePriceError(
                f"Sale price ({sale_price_cents} cents) cannot exceed original price ({original_price_cents} cents)"
            )

        if price_floor_cents is not None:
            if price_floor_cents < 0:
                raise InvalidSalePriceError(f"Price floor cannot be negative: {price_floor_cents}")
            if sale_price_cents < price_floor_cents:
                raise SalePriceBelowFloorError(
                    "Sale price rejected by floor policy",
                    floor_cents=price_floor_cents,
                    offered_cents=sale_price_cents
                )

        discount_cents = original_price_cents - sale_price_cents
        discount_pct = (discount_cents / original_price_cents) * 100.0

        if discount_pct > max_discount_cap_pct:
            raise SaleDiscountCapExceededError(
                "Sale discount rejected by discount cap policy",
                max_cap_pct=max_discount_cap_pct,
                calculated_pct=discount_pct
            )

        return PreservedPriceQuote(
            product_id=product_id,
            sku_id=sku_id,
            original_price_cents=original_price_cents,
            sale_price_cents=sale_price_cents,
            discount_cents=discount_cents,
            discount_percentage=round(discount_pct, 2),
            price_floor_cents=price_floor_cents,
            max_discount_cap_pct=max_discount_cap_pct,
            currency=currency
        )
