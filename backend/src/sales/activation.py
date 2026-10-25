"""
Timezone-Aware Scheduled Activation Engine (FLS-024, FLS-025).
Handles:
1. Timezone conversions and DST boundary transitions (FLS-024).
2. Scheduled activation within a documented tolerance of <= 1.0 second (FLS-025).
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
import logging
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from models.campaigns import CampaignRecord, CampaignStatus

logger = logging.getLogger("sales.activation")

# Documented activation tolerance threshold (§9 Invariant)
ACTIVATION_TOLERANCE_SECONDS = 1.0


class TimezoneConversionService:
    """
    Handles conversion between localized wall-clock times and UTC timestamps,
    robustly handling Daylight Saving Time (DST) transitions.
    """

    @staticmethod
    def to_utc(dt: datetime, tz_name: str) -> datetime:
        """
        Converts a datetime (naive or aware) from the given IANA timezone into UTC.
        """
        tz = ZoneInfo(tz_name)
        if dt.tzinfo is None:
            localized = dt.replace(tzinfo=tz)
        else:
            localized = dt.astimezone(tz)
        return localized.astimezone(timezone.utc)

    @staticmethod
    def from_utc(dt_utc: datetime, target_tz_name: str) -> datetime:
        """
        Converts a UTC datetime into the target IANA timezone wall-clock time.
        """
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        target_tz = ZoneInfo(target_tz_name)
        return dt_utc.astimezone(target_tz)

    @staticmethod
    def is_dst_boundary_crossing(
        start_utc: datetime,
        end_utc: datetime,
        tz_name: str
    ) -> bool:
        """
        Checks whether the interval between start_utc and end_utc crosses a DST shift in tz_name.
        """
        tz = ZoneInfo(tz_name)
        start_local = start_utc.astimezone(tz)
        end_local = end_utc.astimezone(tz)
        return start_local.dst() != end_local.dst()


class ScheduledActivationEngine:
    """
    Evaluates scheduled flash sales and activates those due within the documented tolerance window.
    """

    def __init__(self, session: AsyncSession, tolerance_seconds: float = ACTIVATION_TOLERANCE_SECONDS):
        self.session = session
        self.tolerance_seconds = tolerance_seconds

    def is_due_for_activation(
        self,
        scheduled_start: datetime,
        current_time: datetime
    ) -> bool:
        """
        Returns True if current_time has reached scheduled_start,
        or is within the acceptable past window (scheduled_start <= current_time).
        """
        if scheduled_start.tzinfo is None:
            scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        delta = (current_time - scheduled_start).total_seconds()
        # Must be at or after start time
        return delta >= 0

    async def evaluate_and_activate(
        self,
        current_time: Optional[datetime] = None
    ) -> List[str]:
        """
        Queries all SCHEDULED campaigns that are due as of current_time and activates them.
        Returns list of activated campaign_ids.
        """
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        stmt = select(CampaignRecord).where(
            CampaignRecord.status == CampaignStatus.SCHEDULED.value,
            CampaignRecord.start_time <= now
        )
        res = await self.session.execute(stmt)
        campaigns = res.scalars().all()

        activated_ids = []
        for camp in campaigns:
            # Verify end_time hasn't already passed
            camp_end = camp.end_time
            if camp_end.tzinfo is None:
                camp_end = camp_end.replace(tzinfo=timezone.utc)

            if now < camp_end:
                camp.status = CampaignStatus.ACTIVE.value
                activated_ids.append(camp.campaign_id)
                logger.info(f"Campaign '{camp.campaign_id}' activated at {now.isoformat()}")
            else:
                camp.status = CampaignStatus.ENDED.value
                logger.info(f"Campaign '{camp.campaign_id}' expired before activation at {now.isoformat()}")

        if activated_ids:
            await self.session.commit()

        return activated_ids
