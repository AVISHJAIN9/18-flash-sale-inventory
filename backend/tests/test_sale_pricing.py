import pytest
from datetime import datetime, timezone, timedelta
from models.catalog import ProductSchema
from models.campaigns import CampaignSchema, CampaignStatus
from pricing.pricing import PricingEngine

def test_FLS_019_sale_specific_pricing():
    engine = PricingEngine()
    now = datetime.now(timezone.utc)

    # Product with original price $100 (10000 cents)
    product = ProductSchema(
        product_id="p-audio",
        title="Wireless Headphones",
        original_price_cents=10000
    )

    # 1. No campaign -> regular price
    p1 = engine.resolve_price(product, campaign=None, now=now)
    assert p1["is_flash_sale"] is False
    assert p1["effective_price_cents"] == 10000
    assert p1["discount_cents"] == 0

    # 2. Active campaign during sale window -> sale price $69.99 (6999 cents)
    active_campaign = CampaignSchema(
        campaign_id="camp-audio-flash",
        title="Audio Flash Sale",
        sku_id="sku-audio",
        start_time=now - timedelta(minutes=10),
        end_time=now + timedelta(minutes=50),
        sale_price_cents=6999,
        allocated_stock=100,
        status=CampaignStatus.ACTIVE.value
    )
    p2 = engine.resolve_price(product, campaign=active_campaign, now=now)
    assert p2["is_flash_sale"] is True
    assert p2["campaign_id"] == "camp-audio-flash"
    assert p2["effective_price_cents"] == 6999
    assert p2["original_price_cents"] == 10000
    assert p2["discount_cents"] == 3001

    # 3. Campaign that has not started yet (scheduled in future) -> regular price
    future_campaign = CampaignSchema(
        campaign_id="camp-future",
        title="Future Sale",
        sku_id="sku-audio",
        start_time=now + timedelta(hours=2),
        end_time=now + timedelta(hours=4),
        sale_price_cents=5000,
        allocated_stock=10,
        status=CampaignStatus.ACTIVE.value
    )
    p3 = engine.resolve_price(product, campaign=future_campaign, now=now)
    assert p3["is_flash_sale"] is False
    assert p3["effective_price_cents"] == 10000
