"""
Sale Start and End Scheduling Service (FLS-014).
Handles sale campaign scheduling, time window validation, and lifecycle phase calculation.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field


class SalePhase(str, Enum):
    UPCOMING = "UPCOMING"
    ACTIVE = "ACTIVE"
    ENDED = "ENDED"


class SaleSchedule(BaseModel):
    campaign_id: str
    start_time: datetime
    end_time: datetime
    timezone_name: str = "UTC"

    def duration_seconds(self) -> float:
        return (self.end_time - self.start_time).total_seconds()


class SaleScheduleService:
    """
    Manages scheduling of flash sale start and end windows.
    Supports injectable clock and returns precise timing metrics.
    """

    def validate_schedule(self, start_time: datetime, end_time: datetime) -> None:
        if start_time.tzinfo is None or end_time.tzinfo is None:
            raise ValueError("Start time and end time must be timezone-aware UTC datetimes")
        if end_time <= start_time:
            raise ValueError(f"Sale end_time ({end_time.isoformat()}) must be strictly after start_time ({start_time.isoformat()})")

    def create_schedule(
        self,
        campaign_id: str,
        start_time: datetime,
        end_time: datetime,
        timezone_name: str = "UTC"
    ) -> SaleSchedule:
        self.validate_schedule(start_time, end_time)
        return SaleSchedule(
            campaign_id=campaign_id,
            start_time=start_time,
            end_time=end_time,
            timezone_name=timezone_name
        )

    def evaluate_phase(
        self,
        schedule: SaleSchedule,
        current_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Evaluates the current sale phase (UPCOMING, ACTIVE, ENDED) with exact second counts.
        """
        now = current_time or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        start = schedule.start_time
        end = schedule.end_time
        total_duration = (end - start).total_seconds()

        if now < start:
            starts_in = (start - now).total_seconds()
            return {
                "phase": SalePhase.UPCOMING.value,
                "is_active": False,
                "starts_in_seconds": round(starts_in, 3),
                "remaining_seconds": round((end - now).total_seconds(), 3),
                "total_duration_seconds": total_duration,
                "progress_pct": 0.0,
            }
        elif now >= end:
            ended_ago = (now - end).total_seconds()
            return {
                "phase": SalePhase.ENDED.value,
                "is_active": False,
                "starts_in_seconds": 0.0,
                "remaining_seconds": 0.0,
                "ended_ago_seconds": round(ended_ago, 3),
                "total_duration_seconds": total_duration,
                "progress_pct": 100.0,
            }
        else:
            elapsed = (now - start).total_seconds()
            remaining = (end - now).total_seconds()
            progress = (elapsed / total_duration) * 100.0 if total_duration > 0 else 100.0
            return {
                "phase": SalePhase.ACTIVE.value,
                "is_active": True,
                "starts_in_seconds": 0.0,
                "remaining_seconds": round(remaining, 3),
                "elapsed_seconds": round(elapsed, 3),
                "total_duration_seconds": total_duration,
                "progress_pct": round(progress, 2),
            }
