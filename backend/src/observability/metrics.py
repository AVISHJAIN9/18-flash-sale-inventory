"""
Prometheus Metrics Engine for Flash Sale Inventory Gateway (FLS-127).
Exposes real-time Prometheus gauges, counters, and histograms for stock, checkouts, and incidents.
"""

from typing import Optional
from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.inventory import InventoryRecord

# Dedicated custom registry to avoid collision in test suites
REGISTRY = CollectorRegistry(auto_describe=True)

RESERVATIONS_TOTAL = Counter(
    "flashsale_reservations_total",
    "Total stock reservations placed",
    ["status", "sku_id"],
    registry=REGISTRY
)

ORDERS_TOTAL = Counter(
    "flashsale_orders_total",
    "Total flash sale orders completed or failed",
    ["status", "sku_id"],
    registry=REGISTRY
)

INVENTORY_AVAILABLE = Gauge(
    "flashsale_inventory_available",
    "Real-time available inventory stock",
    ["sku_id"],
    registry=REGISTRY
)

INVENTORY_RESERVED = Gauge(
    "flashsale_inventory_reserved",
    "Real-time reserved inventory stock held in lease",
    ["sku_id"],
    registry=REGISTRY
)

INVENTORY_SOLD = Gauge(
    "flashsale_inventory_sold",
    "Real-time confirmed sold inventory stock",
    ["sku_id"],
    registry=REGISTRY
)

OVERSELL_INCIDENTS_TOTAL = Counter(
    "flashsale_oversell_incidents_total",
    "Total detected inventory oversell and invariant violation incidents",
    ["sku_id", "severity"],
    registry=REGISTRY
)

CHECKOUT_LATENCY_SECONDS = Histogram(
    "flashsale_checkout_duration_seconds",
    "High-concurrency checkout duration in seconds",
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
    registry=REGISTRY
)

async def refresh_inventory_gauges(session: AsyncSession) -> None:
    """
    Refreshes Prometheus gauges from the live database.
    """
    stmt = select(InventoryRecord)
    res = await session.execute(stmt)
    records = res.scalars().all()
    for r in records:
        INVENTORY_AVAILABLE.labels(sku_id=r.sku_id).set(r.available)
        INVENTORY_RESERVED.labels(sku_id=r.sku_id).set(r.reserved)
        INVENTORY_SOLD.labels(sku_id=r.sku_id).set(r.sold)

def export_metrics_text() -> str:
    """
    Renders all registered Prometheus metrics to standard exposition text format.
    """
    return generate_latest(REGISTRY).decode("utf-8")
