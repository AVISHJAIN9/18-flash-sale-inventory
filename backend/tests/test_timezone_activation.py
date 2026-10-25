"""
Tests for Timezone Handling and Scheduled Activation:
- FLS-024: Timezone handling across DST boundary
- FLS-025: Scheduled activation with tolerance, DST boundary injected clock, and real-time test
"""

import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base
from models.catalog import ProductRecord
from models.inventory import InventoryRecord
from models.campaigns import CampaignRecord, CampaignStatus
from sales.activation import (
    TimezoneConversionService,
    ScheduledActivationEngine,
    ACTIVATION_TOLERANCE_SECONDS
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


def test_FLS_024_timezone_handling_across_dst_boundary():
    """
    FLS-024: Timezone handling (BE, P0).
    Verifies (§9 Invariant):
    - Conversion between localized IANA wall-clock times and UTC timestamps
    - Correct DST shift handling across US Eastern daylight savings spring-forward boundary (March 8, 2026)
    - Detection of DST boundary crossing
    """
    svc = TimezoneConversionService()
    tz_name = "America/New_York"

    # US Eastern switches from EST (UTC-5) to EDT (UTC-4) at 2:00 AM on Sunday, March 8, 2026
    before_dst_local = datetime(2026, 3, 8, 1, 30, 0)   # 1:30 AM EST
    after_dst_local = datetime(2026, 3, 8, 3, 30, 0)    # 3:30 AM EDT

    utc_before = svc.to_utc(before_dst_local, tz_name)
    utc_after = svc.to_utc(after_dst_local, tz_name)

    # 1:30 AM EST is 6:30 AM UTC (UTC-5)
    assert utc_before == datetime(2026, 3, 8, 6, 30, 0, tzinfo=timezone.utc)
    # 3:30 AM EDT is 7:30 AM UTC (UTC-4)
    assert utc_after == datetime(2026, 3, 8, 7, 30, 0, tzinfo=timezone.utc)

    # Elapsed real time between 1:30 AM EST and 3:30 AM EDT is exactly 1 hour (not 2 hours)
    delta_seconds = (utc_after - utc_before).total_seconds()
    assert delta_seconds == 3600.0

    # Verify detection of DST boundary crossing
    assert svc.is_dst_boundary_crossing(utc_before, utc_after, tz_name) is True

    # Convert back to local time and verify wall clock preservation
    restored_before = svc.from_utc(utc_before, tz_name)
    assert restored_before.hour == 1 and restored_before.minute == 30
    restored_after = svc.from_utc(utc_after, tz_name)
    assert restored_after.hour == 3 and restored_after.minute == 30


@pytest.mark.asyncio
async def test_FLS_025_scheduled_activation_dst_injected_clock(db_session):
    """
    FLS-025: Scheduled activation with injected clock across DST boundary (§9 Invariant).
    Verifies:
    - Campaign scheduled right across DST boundary activates exactly at scheduled time
    - Scheduled activation fires within documented tolerance (<= 1.0 second)
    - Database state updates to ACTIVE
    """
    svc = TimezoneConversionService()
    tz_name = "America/New_York"
    # Scheduled to start at 3:30 AM EDT (7:30 AM UTC on March 8, 2026)
    sale_start_local = datetime(2026, 3, 8, 3, 30, 0)
    sale_start_utc = svc.to_utc(sale_start_local, tz_name)
    sale_end_utc = sale_start_utc + timedelta(hours=2)

    # Seed inventory SKU
    prod = ProductRecord(product_id="prod-phone-dst", title="DST Phone", original_price_cents=50000)
    inv = InventoryRecord(sku_id="sku-dst-1", product_id="prod-phone-dst", total_allocated=100, available=100, reserved=0, sold=0, version=1)
    db_session.add(prod)
    db_session.add(inv)
    await db_session.commit()

    campaign = CampaignRecord(
        campaign_id="camp-dst-launch",
        title="Spring DST Midnight Flash Sale",
        sku_id="sku-dst-1",
        start_time=sale_start_utc,
        end_time=sale_end_utc,
        sale_price_cents=35000,
        allocated_stock=100,
        per_user_limit=2,
        status=CampaignStatus.SCHEDULED.value
    )
    db_session.add(campaign)
    await db_session.commit()

    engine = ScheduledActivationEngine(session=db_session, tolerance_seconds=ACTIVATION_TOLERANCE_SECONDS)

    # 1. Injected clock 5 seconds BEFORE start time -> remains SCHEDULED
    time_before = sale_start_utc - timedelta(seconds=5)
    activated = await engine.evaluate_and_activate(current_time=time_before)
    assert "camp-dst-launch" not in activated

    camp_status = (await db_session.execute(select(CampaignRecord).where(CampaignRecord.campaign_id == "camp-dst-launch"))).scalars().first()
    assert camp_status.status == CampaignStatus.SCHEDULED.value

    # 2. Injected clock AT start time (within tolerance 0.0s) -> activates immediately
    time_at_start = sale_start_utc
    activated = await engine.evaluate_and_activate(current_time=time_at_start)
    assert "camp-dst-launch" in activated

    camp_status = (await db_session.execute(select(CampaignRecord).where(CampaignRecord.campaign_id == "camp-dst-launch"))).scalars().first()
    assert camp_status.status == CampaignStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_FLS_025_scheduled_activation_real_time(db_session):
    """
    FLS-025: Scheduled activation real-time execution test (§9 Invariant).
    Verifies that scheduled activation fires within documented tolerance in real time.
    """
    # Seed inventory SKU
    prod = ProductRecord(product_id="prod-rt-1", title="RT Watch", original_price_cents=20000)
    inv = InventoryRecord(sku_id="sku-rt-1", product_id="prod-rt-1", total_allocated=50, available=50, reserved=0, sold=0, version=1)
    db_session.add(prod)
    db_session.add(inv)
    await db_session.commit()

    # Schedule campaign 0.05 seconds into future
    now_real = datetime.now(timezone.utc)
    start_real = now_real + timedelta(seconds=0.05)
    end_real = start_real + timedelta(minutes=10)

    campaign = CampaignRecord(
        campaign_id="camp-rt-test",
        title="Real Time Activation Test",
        sku_id="sku-rt-1",
        start_time=start_real,
        end_time=end_real,
        sale_price_cents=15000,
        allocated_stock=50,
        per_user_limit=1,
        status=CampaignStatus.SCHEDULED.value
    )
    db_session.add(campaign)
    await db_session.commit()

    engine = ScheduledActivationEngine(session=db_session, tolerance_seconds=ACTIVATION_TOLERANCE_SECONDS)

    # Before start: should not activate
    act_premature = await engine.evaluate_and_activate(current_time=datetime.now(timezone.utc))
    assert "camp-rt-test" not in act_premature

    # Wait for the scheduled window in real time
    await asyncio.sleep(0.08)  # wait for real-time activation window to arrive

    # After wait: real time has passed start_real, activation fires within tolerance
    act_real = await engine.evaluate_and_activate(current_time=datetime.now(timezone.utc))
    assert "camp-rt-test" in act_real

    camp_status = (await db_session.execute(select(CampaignRecord).where(CampaignRecord.campaign_id == "camp-rt-test"))).scalars().first()
    assert camp_status.status == CampaignStatus.ACTIVE.value
