import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import update
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, InventoryRecord, ReservationRecord, ReservationStatus
from stock.reconciliation import StockReconciliationService
from datetime import datetime, timezone, timedelta

@pytest_asyncio.fixture
async def async_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_049_stock_reconciliation(async_session):
    """
    FLS-049: Stock reconciliation.
    Audits inventory against active reservations and confirmed orders, detects drift,
    and reconciles numbers back to absolute truth.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-recon", title="Recon Item", original_price_cents=10000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-recon", "prod-recon", total_allocated=10)

    # Insert 2 pending active reservations (quantity 3 and 2)
    now = datetime.now(timezone.utc)
    res1 = ReservationRecord(
        reservation_id="res-recon-1",
        sku_id="sku-recon",
        user_id="user-1",
        quantity=3,
        status=ReservationStatus.PENDING.value,
        expires_at=now + timedelta(minutes=5)
    )
    res2 = ReservationRecord(
        reservation_id="res-recon-2",
        sku_id="sku-recon",
        user_id="user-2",
        quantity=2,
        status=ReservationStatus.PENDING.value,
        expires_at=now + timedelta(minutes=5)
    )
    async_session.add_all([res1, res2])
    await async_session.commit()

    service = StockReconciliationService(async_session)

    # 1. Audit before reconciliation detects drift because inventory was not decremented
    audit_pre = await service.audit_sku("sku-recon")
    assert audit_pre["has_discrepancy"] is True
    assert audit_pre["ledger_truth"]["active_reserved"] == 5
    assert audit_pre["ledger_truth"]["expected_available"] == 5
    assert audit_pre["recorded"]["available"] == 10

    # 2. Reconcile corrects inventory table to match ledger truth
    result = await service.reconcile_sku("sku-recon")
    assert result["status"] == "RECONCILED"
    assert result["corrected"]["available"] == 5
    assert result["corrected"]["reserved"] == 5
    assert result["corrected"]["sold"] == 0

    # 3. Post-reconciliation audit reports no discrepancy
    audit_post = await service.audit_sku("sku-recon")
    assert audit_post["has_discrepancy"] is False
    assert audit_post["is_conserved"] is True
    assert audit_post["recorded"]["available"] == 5
    assert audit_post["recorded"]["reserved"] == 5
