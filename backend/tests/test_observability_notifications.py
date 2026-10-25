import json
import pytest
import pytest_asyncio
import httpx
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text
from db.database import Base, get_db
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, InventoryRecord
from api.app import app
from observability.metrics import RESERVATIONS_TOTAL, export_metrics_text, refresh_inventory_gauges
from observability.logging import StructuredLogger
from observability.oversell import OversellDetector, OversellIncident

@pytest_asyncio.fixture
async def obs_client():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with session_maker() as session:
        pm = ProductManager(session)
        await pm.create_product(ProductSchema(product_id="prod-obs-1", title="Obs Drone", original_price_cents=30000))
        im = InventoryManager(session)
        await im.initialize_inventory("sku-obs-1", "prod-obs-1", total_allocated=50)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, session_maker

    app.dependency_overrides.clear()
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_127_prometheus_metrics(obs_client):
    """
    FLS-127: Prometheus metrics export verification.
    Asserts /metrics endpoint renders live gauges and counters in Prometheus text format.
    """
    client, _ = obs_client

    # Record some reservations in counter
    RESERVATIONS_TOTAL.labels(status="confirmed", sku_id="sku-obs-1").inc(5)

    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    text = resp.text

    assert "flashsale_reservations_total" in text
    assert 'flashsale_reservations_total{sku_id="sku-obs-1",status="confirmed"} 5.0' in text
    assert "flashsale_inventory_available" in text
    assert 'flashsale_inventory_available{sku_id="sku-obs-1"} 50.0' in text
    assert "flashsale_oversell_incidents_total" in text

def test_FLS_129_structured_logs():
    """
    FLS-129: Structured JSON logging verification.
    Asserts schema compliance, contextual tagging, and credential redaction.
    """
    logger = StructuredLogger(name="test.flashsale.logger")
    logger.clear_captured_logs()

    entry = logger.info(
        event="CHECKOUT_PROCESSED",
        message="Checkout order completed successfully",
        sku_id="sku-obs-99",
        user_id="user-vip-1",
        trace_id="trc-abc-123",
        data={
            "quantity": 2,
            "amount_cents": 60000,
            "password": "SuperSecretPassword123!",
            "credit_card": "4111-2222-3333-4444"
        }
    )

    assert entry["level"] == "INFO"
    assert entry["event"] == "CHECKOUT_PROCESSED"
    assert entry["sku_id"] == "sku-obs-99"
    assert entry["user_id"] == "user-vip-1"
    assert entry["trace_id"] == "trc-abc-123"

    # Redaction test
    assert entry["data"]["password"] == "[REDACTED]"
    assert entry["data"]["credit_card"] == "[REDACTED]"
    assert entry["data"]["amount_cents"] == 60000

    # Ensure captured log is serialized JSON
    captured = logger.get_captured_logs()
    assert len(captured) == 1
    serialized = json.dumps(captured[0])
    parsed = json.loads(serialized)
    assert parsed["event"] == "CHECKOUT_PROCESSED"

@pytest.mark.asyncio
async def test_FLS_135_oversell_incidents(obs_client):
    """
    FLS-135: Oversell and stock conservation invariant detection.
    Verifies detection of corrupted inventory records (available + reserved + sold != allocated).
    """
    client, session_maker = obs_client
    detector = OversellDetector()

    # 1. Normal state should report 0 violations
    async with session_maker() as session:
        inc = await detector.audit_sku(session, "sku-obs-1")
        assert inc is None

    # 2. Corrupt the row intentionally to simulate race condition / oversell (bypassing DB constraint)
    async with session_maker() as session:
        await session.execute(text("PRAGMA ignore_check_constraints = ON;"))
        await session.execute(text("UPDATE inventory SET sold = 60, available = 0, reserved = 0 WHERE sku_id = 'sku-obs-1'"))
        await session.commit()

    # 3. Audit again - must detect violation
    async with session_maker() as session:
        incident = await detector.audit_sku(session, "sku-obs-1")
        assert incident is not None
        assert incident.sku_id == "sku-obs-1"
        assert incident.total_allocated == 50
        assert incident.sold == 60
        assert incident.discrepancy == 10
        assert incident.severity == "CRITICAL"
        assert "Stock conservation anomaly" in incident.message

    # 4. Test API endpoint detection
    audit_resp = await client.post("/api/v1/incidents/audit?sku_id=sku-obs-1")
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["incidents_detected_count"] == 1
    assert audit_data["incidents"][0]["sku_id"] == "sku-obs-1"
    assert audit_data["incidents"][0]["discrepancy"] == 10
