"""
Unit and Integration Tests for Flash Sale Core Features:
- FLS-014: Sale start/end scheduling
- FLS-020: Original-price preservation
- FLS-021: Sale-price validation
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base
from models.catalog import ProductRecord
from models.inventory import InventoryRecord
from models.campaigns import CampaignRecord, CampaignStatus
from sales.scheduling import SaleScheduleService, SalePhase
from pricing.validation import (
    SalePriceValidator,
    InvalidSalePriceError,
    SalePriceBelowFloorError,
    SaleDiscountCapExceededError
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


def test_FLS_014_sale_start_end_scheduling():
    """
    FLS-014: Sale start/end scheduling (BE, P0).
    Verifies:
    - Time window validation (end_time must be strictly after start_time)
    - Precise phase calculation (UPCOMING, ACTIVE, ENDED) with injectable clock
    - Elapsed, remaining, and progress percentage computation
    """
    service = SaleScheduleService()
    now_base = datetime(2026, 11, 1, 12, 0, 0, tzinfo=timezone.utc)
    start_time = now_base + timedelta(hours=2)   # 14:00
    end_time = now_base + timedelta(hours=6)     # 18:00

    # 1. Reject invalid scheduling window
    with pytest.raises(ValueError) as exc:
        service.create_schedule(
            campaign_id="sale-invalid",
            start_time=end_time,
            end_time=start_time
        )
    assert "must be strictly after start_time" in str(exc.value)

    # 2. Valid schedule creation
    schedule = service.create_schedule(
        campaign_id="sale-cyber-monday",
        start_time=start_time,
        end_time=end_time
    )
    assert schedule.duration_seconds() == 14400.0  # 4 hours

    # 3. UPCOMING phase (clock at 12:00, 2h before start)
    phase_upcoming = service.evaluate_phase(schedule, current_time=now_base)
    assert phase_upcoming["phase"] == SalePhase.UPCOMING.value
    assert phase_upcoming["is_active"] is False
    assert phase_upcoming["starts_in_seconds"] == 7200.0
    assert phase_upcoming["progress_pct"] == 0.0

    # 4. ACTIVE phase (clock at 15:00, 1h into 4h sale = 25% progress)
    phase_active = service.evaluate_phase(schedule, current_time=start_time + timedelta(hours=1))
    assert phase_active["phase"] == SalePhase.ACTIVE.value
    assert phase_active["is_active"] is True
    assert phase_active["elapsed_seconds"] == 3600.0
    assert phase_active["remaining_seconds"] == 10800.0
    assert phase_active["progress_pct"] == 25.0

    # 5. ENDED phase (clock at 19:00, 1h after end)
    phase_ended = service.evaluate_phase(schedule, current_time=end_time + timedelta(hours=1))
    assert phase_ended["phase"] == SalePhase.ENDED.value
    assert phase_ended["is_active"] is False
    assert phase_ended["ended_ago_seconds"] == 3600.0
    assert phase_ended["remaining_seconds"] == 0.0
    assert phase_ended["progress_pct"] == 100.0


@pytest.mark.asyncio
async def test_FLS_020_original_price_preservation(db_session):
    """
    FLS-020: Original-price preservation (BE, P0).
    Verifies (§9 Invariant):
    - Original price preserved and returned in all responses
    - Database product record's baseline original_price_cents is strictly preserved
    - Quote accurately includes original, effective sale price, and discount
    """
    # 1. Create baseline product with original price $120.00 (12000 cents)
    product = ProductRecord(
        product_id="prod-laptop-99",
        title="Pro Laptop 15",
        original_price_cents=12000
    )
    db_session.add(product)
    await db_session.commit()

    # 2. Generate sale quote with original price preservation
    validator = SalePriceValidator()
    quote = validator.validate_and_quote(
        product_id=product.product_id,
        original_price_cents=product.original_price_cents,
        sale_price_cents=8400,  # 30% discount = $84.00
        sku_id="sku-laptop-silver"
    )

    # Invariant: Original price preserved and returned alongside sale price
    assert quote.original_price_cents == 12000
    assert quote.sale_price_cents == 8400
    assert quote.discount_cents == 3600
    assert quote.discount_percentage == 30.0

    # 3. Verify in database that ProductRecord original_price_cents was not modified
    db_prod = (await db_session.execute(
        select(ProductRecord).where(ProductRecord.product_id == "prod-laptop-99")
    )).scalars().first()
    assert db_prod.original_price_cents == 12000


def test_FLS_021_sale_price_validation():
    """
    FLS-021: Sale-price validation (BE, P0).
    Verifies (§9 Invariant):
    - sale-price >= floor
    - max total discount <= cap
    - sale_price <= original_price
    - invalid pricing attempts raise typed exceptions
    """
    validator = SalePriceValidator()
    original_cents = 10000  # $100.00

    # 1. Valid sale price passing floor and discount cap
    valid_quote = validator.validate_and_quote(
        product_id="prod-item-1",
        original_price_cents=original_cents,
        sale_price_cents=4000,       # $40.00 (60% discount)
        price_floor_cents=3000,      # floor $30.00
        max_discount_cap_pct=75.0    # cap 75%
    )
    assert valid_quote.sale_price_cents == 4000
    assert valid_quote.discount_cents == 6000
    assert valid_quote.discount_percentage == 60.0

    # 2. Reject sale price exceeding original price
    with pytest.raises(InvalidSalePriceError) as exc_higher:
        validator.validate_and_quote(
            product_id="prod-item-1",
            original_price_cents=original_cents,
            sale_price_cents=12000  # $120.00 > $100.00
        )
    assert "cannot exceed original price" in str(exc_higher.value)

    # 3. Reject negative or zero sale price
    with pytest.raises(InvalidSalePriceError) as exc_zero:
        validator.validate_and_quote(
            product_id="prod-item-1",
            original_price_cents=original_cents,
            sale_price_cents=0
        )
    assert "strictly positive" in str(exc_zero.value)

    # 4. Reject sale price below configured minimum floor (§9 Invariant)
    with pytest.raises(SalePriceBelowFloorError) as exc_floor:
        validator.validate_and_quote(
            product_id="prod-item-1",
            original_price_cents=original_cents,
            sale_price_cents=2500,     # $25.00
            price_floor_cents=3000     # floor $30.00
        )
    assert exc_floor.value.floor_cents == 3000
    assert exc_floor.value.offered_cents == 2500

    # 5. Reject discount exceeding max total discount cap (§9 Invariant)
    with pytest.raises(SaleDiscountCapExceededError) as exc_cap:
        validator.validate_and_quote(
            product_id="prod-item-1",
            original_price_cents=original_cents,
            sale_price_cents=1500,       # $15.00 -> 85% discount
            max_discount_cap_pct=80.0    # cap 80%
        )
    assert exc_cap.value.max_cap_pct == 80.0
    assert exc_cap.value.calculated_pct == 85.0
