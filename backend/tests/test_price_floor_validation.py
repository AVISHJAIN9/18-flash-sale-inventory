import pytest
from pricing.pricing import PricingEngine

def test_FLS_062_price_floor_validation():
    """
    FLS-062: Price-floor validation.
    Enforces minimum allowable selling price floor, preventing excessive discounting
    or loss-leading below configured margin bounds.
    """
    engine = PricingEngine()

    # 1. Direct validation: $50 sale price against $40 floor -> valid
    assert engine.validate_price_floor(sale_price_cents=5000, price_floor_cents=4000) is True

    # 2. Direct validation: $30 sale price against $40 floor -> invalid (below floor)
    assert engine.validate_price_floor(sale_price_cents=3000, price_floor_cents=4000) is False

    # 3. Exact boundary match: $40 sale price against $40 floor -> valid
    assert engine.validate_price_floor(sale_price_cents=4000, price_floor_cents=4000) is True

    # 4. Enforce floor via apply_percentage_discount:
    # 50% discount on $100 (10000 cents) normally yields $50 (5000 cents).
    # If price floor is $60 (6000 cents), price must be clamped to $60, discount clamped to $40.
    res = engine.apply_percentage_discount(
        original_price_cents=10000,
        discount_percentage=50.0,
        price_floor_cents=6000
    )
    assert res["floor_enforced"] is True
    assert res["effective_price_cents"] == 6000
    assert res["discount_cents"] == 4000

    # 5. When discounted price is above floor, floor is not enforced
    res2 = engine.apply_percentage_discount(
        original_price_cents=10000,
        discount_percentage=20.0,
        price_floor_cents=6000
    )
    assert res2["floor_enforced"] is False
    assert res2["effective_price_cents"] == 8000
    assert res2["discount_cents"] == 2000

    # 6. Negative price floor raises ValueError
    with pytest.raises(ValueError):
        engine.validate_price_floor(sale_price_cents=5000, price_floor_cents=-100)
