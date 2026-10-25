import pytest
from pricing.pricing import PricingEngine

def test_FLS_053_percentage_discount():
    """
    FLS-053: Percentage discount.
    Validates accurate percentage-based price reduction in exact cents, bound checks,
    and deterministic integer rounding.
    """
    engine = PricingEngine()

    # 1. 20% discount on $100.00 (10000 cents) -> $80.00 (8000 cents)
    res1 = engine.apply_percentage_discount(original_price_cents=10000, discount_percentage=20.0)
    assert res1["discount_percentage"] == 20.0
    assert res1["discount_cents"] == 2000
    assert res1["effective_price_cents"] == 8000

    # 2. 33.33% discount on $29.99 (2999 cents) -> round(2999 * 0.3333) = round(999.5667) = 1000 cents
    res2 = engine.apply_percentage_discount(original_price_cents=2999, discount_percentage=33.33)
    assert res2["discount_cents"] == 1000
    assert res2["effective_price_cents"] == 1999

    # 3. 0% discount -> full original price
    res3 = engine.apply_percentage_discount(original_price_cents=5000, discount_percentage=0.0)
    assert res3["discount_cents"] == 0
    assert res3["effective_price_cents"] == 5000

    # 4. 100% discount -> 0 cents
    res4 = engine.apply_percentage_discount(original_price_cents=5000, discount_percentage=100.0)
    assert res4["discount_cents"] == 5000
    assert res4["effective_price_cents"] == 0

    # 5. Invalid percentage bounds (>100 or <0) raise ValueError
    with pytest.raises(ValueError):
        engine.apply_percentage_discount(original_price_cents=5000, discount_percentage=-5.0)

    with pytest.raises(ValueError):
        engine.apply_percentage_discount(original_price_cents=5000, discount_percentage=105.0)
