"""
Tests for Orders & Payments:
- FLS-094: Payment failure handling
- FLS-095: Payment retry
- FLS-098: Order cancellation
- FLS-099: Refund initiation
- FLS-100: Refund status
- FLS-101: Inventory-to-order consistency
"""

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base
from models.catalog import ProductRecord
from models.inventory import InventoryRecord
from models.orders import OrderRecord, OrderStatus
from models.payments import PaymentRecord, PaymentStatus, RefundRecord, RefundStatus
from flow.order_payments import OrderPaymentService


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_FLS_094_payment_failure_handling(db_session):
    """
    FLS-094: Payment failure handling (BE+DB, P0).
    Verifies:
    - Failure recording transitions payment status to FAILED
    - Records error code and message
    """
    svc = OrderPaymentService(db_session)
    # Seed payment record
    pay = PaymentRecord(
        payment_id="pay-fail-1",
        order_id="ord-fail-1",
        payment_provider="stripe_flash",
        amount_cents=15000,
        status=PaymentStatus.INITIATED.value,
        idempotency_key="idemp-fail-1"
    )
    db_session.add(pay)
    await db_session.commit()

    failed_pay = await svc.handle_payment_failure(
        order_id="ord-fail-1",
        payment_id="pay-fail-1",
        error_code="INSUFFICIENT_FUNDS",
        error_message="Card declined by issuing bank"
    )
    assert failed_pay.status == PaymentStatus.FAILED.value
    assert failed_pay.error_code == "INSUFFICIENT_FUNDS"


@pytest.mark.asyncio
async def test_FLS_095_payment_retry_idempotent(db_session):
    """
    FLS-095: Payment retry (BE+DB, P0).
    Verifies (§9 Invariant):
    - Payment retry is idempotent (one charge)
    - Re-executing with the same idempotency key returns the existing successful charge
    """
    prod = ProductRecord(product_id="prod-retry-1", title="Retry Laptop", original_price_cents=100000)
    inv = InventoryRecord(sku_id="sku-retry-laptop", product_id="prod-retry-1", total_allocated=5, available=4, reserved=1, sold=0, version=1)
    order = OrderRecord(
        order_id="ord-retry-1",
        user_id="user_retry",
        sku_id="sku-retry-laptop",
        quantity=1,
        unit_price_cents=100000,
        total_amount_cents=100000,
        status=OrderStatus.PENDING.value,
        idempotency_key="idemp-order-retry-1"
    )
    db_session.add(prod)
    db_session.add(inv)
    db_session.add(order)
    await db_session.commit()

    svc = OrderPaymentService(db_session)

    # 1. First payment retry attempt succeeds
    ok1, msg1, pay1 = await svc.retry_payment_idempotent(
        order_id="ord-retry-1",
        idempotency_key="pay-key-retry-123",
        simulated_charge_success=True
    )
    assert ok1 is True
    assert pay1.status == PaymentStatus.SUCCESS.value
    assert order.status == OrderStatus.PAID.value

    # 2. Second retry attempt with same idempotency key returns existing charge without double-charging (§9 Invariant)
    ok2, msg2, pay2 = await svc.retry_payment_idempotent(
        order_id="ord-retry-1",
        idempotency_key="pay-key-retry-123"
    )
    assert ok2 is True
    assert pay2.payment_id == pay1.payment_id
    assert "already succeeded" in msg2


@pytest.mark.asyncio
async def test_FLS_098_order_cancellation(db_session):
    """
    FLS-098: Order cancellation (BE+DB, P0).
    Verifies:
    - Order transitions from PENDING to CANCELLED
    - Held inventory stock is automatically released back to available pool
    """
    prod = ProductRecord(product_id="prod-cancel-1", title="Cancel Speaker", original_price_cents=12000)
    inv = InventoryRecord(sku_id="sku-cancel-speaker", product_id="prod-cancel-1", total_allocated=10, available=7, reserved=3, sold=0, version=1)
    order = OrderRecord(
        order_id="ord-cancel-1",
        user_id="user_cancel",
        sku_id="sku-cancel-speaker",
        quantity=3,
        unit_price_cents=12000,
        total_amount_cents=36000,
        status=OrderStatus.PENDING.value,
        idempotency_key="idemp-cancel-1"
    )
    db_session.add(prod)
    db_session.add(inv)
    db_session.add(order)
    await db_session.commit()

    svc = OrderPaymentService(db_session)
    cancelled_order = await svc.cancel_order("ord-cancel-1", reason="Changed mind")
    assert cancelled_order.status == OrderStatus.CANCELLED.value

    # Verify inventory was restored
    inv_updated = (await db_session.execute(
        select(InventoryRecord).where(InventoryRecord.sku_id == "sku-cancel-speaker")
    )).scalars().first()
    assert inv_updated.available == 10
    assert inv_updated.reserved == 0
    assert inv_updated.sold == 0


@pytest.mark.asyncio
async def test_FLS_099_refund_initiation_idempotent(db_session):
    """
    FLS-099: Refund initiation (BE+DB, P0).
    Verifies (§9 Invariant):
    - Refunds are idempotent and never exceed the captured amount
    - Full refund updates order to REFUNDED
    """
    prod = ProductRecord(product_id="prod-ref-1", title="Refund Tablet", original_price_cents=40000)
    inv = InventoryRecord(sku_id="sku-ref-tablet", product_id="prod-ref-1", total_allocated=10, available=9, reserved=0, sold=1, version=1)
    order = OrderRecord(
        order_id="ord-ref-1",
        user_id="user_ref",
        sku_id="sku-ref-tablet",
        quantity=1,
        unit_price_cents=40000,
        total_amount_cents=40000,
        status=OrderStatus.PAID.value,
        idempotency_key="idemp-ord-ref-1"
    )
    pay = PaymentRecord(
        payment_id="pay-ref-1",
        order_id="ord-ref-1",
        payment_provider="stripe_flash",
        amount_cents=40000,
        status=PaymentStatus.SUCCESS.value,
        idempotency_key="idemp-pay-ref-1"
    )
    db_session.add(prod)
    db_session.add(inv)
    db_session.add(order)
    db_session.add(pay)
    await db_session.commit()

    svc = OrderPaymentService(db_session)

    # 1. Attempting refund exceeding captured amount rejects (§9 Invariant)
    with pytest.raises(ValueError) as exc:
        await svc.initiate_refund(
            order_id="ord-ref-1",
            payment_id="pay-ref-1",
            amount_cents=50000,  # $500 > $400 captured
            idempotency_key="ref-key-excess"
        )
    assert "cannot exceed captured payment amount" in str(exc.value)

    # 2. Valid refund of $400.00
    ref1 = await svc.initiate_refund(
        order_id="ord-ref-1",
        payment_id="pay-ref-1",
        amount_cents=40000,
        idempotency_key="ref-key-1"
    )
    assert ref1.status == RefundStatus.SUCCESS.value
    assert ref1.amount_cents == 40000
    assert order.status == OrderStatus.REFUNDED.value

    # 3. Idempotent replay with same key returns existing refund record
    ref2 = await svc.initiate_refund(
        order_id="ord-ref-1",
        payment_id="pay-ref-1",
        amount_cents=40000,
        idempotency_key="ref-key-1"
    )
    assert ref2.refund_id == ref1.refund_id


@pytest.mark.asyncio
async def test_FLS_100_refund_status(db_session):
    """
    FLS-100: Refund status (BE+DB, P0).
    Verifies retrieval of refund status and metadata.
    """
    ref = RefundRecord(
        refund_id="ref-status-query-1",
        payment_id="pay-stat-1",
        order_id="ord-stat-1",
        amount_cents=12500,
        idempotency_key="idemp-ref-stat-1",
        status=RefundStatus.SUCCESS.value,
        reason="Defective on arrival"
    )
    db_session.add(ref)
    await db_session.commit()

    svc = OrderPaymentService(db_session)
    res = await svc.get_refund_status("ref-status-query-1")
    assert res is not None
    assert res["status"] == "SUCCESS"
    assert res["amount_cents"] == 12500
    assert res["reason"] == "Defective on arrival"


@pytest.mark.asyncio
async def test_FLS_101_inventory_to_order_consistency(db_session):
    """
    FLS-101: Inventory-to-order consistency (BE+DB, P0).
    Verifies (§9 Invariant):
    - Inventory-to-order consistency job detects an intentionally corrupted row
    - Returns exact drift and discrepancy details
    """
    prod = ProductRecord(product_id="prod-audit-1", title="Audit Phone", original_price_cents=80000)
    db_session.add(prod)

    # 1. Clean consistent inventory row: sold=2, matching 2 paid orders
    inv_clean = InventoryRecord(sku_id="sku-audit-clean", product_id="prod-audit-1", total_allocated=10, available=8, reserved=0, sold=2, version=1)
    order_clean = OrderRecord(
        order_id="ord-audit-clean-1",
        user_id="user_audit_1",
        sku_id="sku-audit-clean",
        quantity=2,
        unit_price_cents=80000,
        total_amount_cents=160000,
        status=OrderStatus.PAID.value,
        idempotency_key="idemp-audit-clean-1"
    )

    # 2. Corrupted row (§9 Invariant): Intentionally corrupted sold=5 while only 1 paid order exists
    inv_corrupt = InventoryRecord(sku_id="sku-audit-corrupt", product_id="prod-audit-1", total_allocated=10, available=5, reserved=0, sold=5, version=1)
    order_corrupt = OrderRecord(
        order_id="ord-audit-corrupt-1",
        user_id="user_audit_2",
        sku_id="sku-audit-corrupt",
        quantity=1,
        unit_price_cents=80000,
        total_amount_cents=80000,
        status=OrderStatus.PAID.value,
        idempotency_key="idemp-audit-corrupt-1"
    )

    db_session.add(inv_clean)
    db_session.add(order_clean)
    db_session.add(inv_corrupt)
    db_session.add(order_corrupt)
    await db_session.commit()

    svc = OrderPaymentService(db_session)
    discrepancies = await svc.audit_inventory_to_order_consistency()

    # The clean SKU must not have any discrepancy
    clean_discrepancies = [d for d in discrepancies if d["sku_id"] == "sku-audit-clean"]
    assert len(clean_discrepancies) == 0

    # The intentionally corrupted SKU MUST be detected
    corrupt_discrepancies = [d for d in discrepancies if d["sku_id"] == "sku-audit-corrupt"]
    assert len(corrupt_discrepancies) == 1
    d = corrupt_discrepancies[0]
    assert d["inventory_sold"] == 5
    assert d["orders_paid"] == 1
    assert d["sold_drift"] == 4
    assert d["is_sold_consistent"] is False
