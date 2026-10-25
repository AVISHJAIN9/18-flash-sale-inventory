"""
Oversell Incident Detection and Invariant Integrity Auditor (FLS-135).
Detects discrepancies where stock conservation invariant (Available + Reserved + Sold == Total)
is violated or available drops below zero.
"""

import uuid
import datetime
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.inventory import InventoryRecord
from observability.logging import global_structured_logger
from observability.metrics import OVERSELL_INCIDENTS_TOTAL

@dataclass
class OversellIncident:
    incident_id: str
    sku_id: str
    total_allocated: int
    available: int
    reserved: int
    sold: int
    sum_quantities: int
    discrepancy: int
    severity: str
    message: str
    detected_at: str

class OversellDetector:
    """
    Continuous audit monitor to catch, report, and alert on oversell anomalies.
    """
    def __init__(self):
        self._incidents: List[OversellIncident] = []

    async def audit_sku(self, session: AsyncSession, sku_id: str) -> Optional[OversellIncident]:
        """
        Audits a single SKU against stock conservation rules.
        """
        stmt = select(InventoryRecord).where(InventoryRecord.sku_id == sku_id)
        res = await session.execute(stmt)
        record = res.scalars().first()
        if not record:
            return None

        sum_q = record.available + record.reserved + record.sold
        discrepancy = sum_q - record.total_allocated

        # Check for oversell or invariant violation
        is_violation = (discrepancy != 0) or (record.available < 0) or (record.sold > record.total_allocated)
        if not is_violation:
            return None

        severity = "CRITICAL" if (record.available < 0 or record.sold > record.total_allocated) else "WARNING"
        incident = OversellIncident(
            incident_id=f"inc-{uuid.uuid4().hex[:10]}",
            sku_id=record.sku_id,
            total_allocated=record.total_allocated,
            available=record.available,
            reserved=record.reserved,
            sold=record.sold,
            sum_quantities=sum_q,
            discrepancy=discrepancy,
            severity=severity,
            message=f"Stock conservation anomaly on SKU '{record.sku_id}': A({record.available}) + R({record.reserved}) + S({record.sold}) = {sum_q} != {record.total_allocated}",
            detected_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )

        self._incidents.append(incident)
        OVERSELL_INCIDENTS_TOTAL.labels(sku_id=record.sku_id, severity=severity).inc()

        global_structured_logger.error(
            event="OVERSELL_INCIDENT_DETECTED",
            message=incident.message,
            sku_id=record.sku_id,
            data=asdict(incident)
        )
        return incident

    async def audit_all_inventory(self, session: AsyncSession) -> List[OversellIncident]:
        """
        Performs full table scan audit across all inventory SKUs.
        """
        stmt = select(InventoryRecord)
        res = await session.execute(stmt)
        records = res.scalars().all()

        detected = []
        for r in records:
            inc = await self.audit_sku(session, r.sku_id)
            if inc:
                detected.append(inc)
        return detected

    def get_incidents(self, sku_id: Optional[str] = None) -> List[OversellIncident]:
        if sku_id:
            return [i for i in self._incidents if i.sku_id == sku_id]
        return list(self._incidents)

    def clear_incidents(self) -> None:
        self._incidents.clear()

global_oversell_detector = OversellDetector()
