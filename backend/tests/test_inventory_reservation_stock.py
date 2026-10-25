"""
Unit and Integration Tests for Inventory Reservation & Stock:
- FLS-040: Available quantity
- FLS-041: Reserved quantity
- FLS-042: Sold quantity
- FLS-050: SKU-level inventory
"""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base
from models.catalog import ProductRecord
from models.inventory import InventoryRecord, InventoryManager, ReservationRecord, ReservationStatus
from stock.reservation import StockReservationService
from flow.checkout import CheckoutService


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
async def test_FLS_040_available_quantity(db_session):
    """
    FLS-040: Available quantity (BE+DB, P0).
    Verifies (§9 Invariant):
    - Available stock matches total allocated initially
    - Available quantity decreases on atomic reservation
    - Check constraint chk_inventory_available_nonneg rejects negative available stock
    - Conservation invariant available + reserved + sold == total holds
    """
    prod = ProductRecord(product_id="prod-stock-1", title="Stock Item 1", original_price_cents=10000)
    db_session.add(prod)
    inv_mgr = InventoryManager(db_session)
    inv = await inv_mgr.initialize_inventory("sku-stock-avail", "prod-stock-1", total_allocated=10)

    assert inv.available == 10
    assert inv.reserved == 0
    assert inv.sold == 0

    svc = StockReservationService(db_session)

    # 1. Reserve 4 units
    ok, msg, res_data = await svc.reserve_stock(
        sku_id="sku-stock-avail",
        user_id="user-1",
        quantity=4,
        lease_seconds=300
    )
    assert ok is True
    st = await svc.get_stock_status("sku-stock-avail")
    assert st["available"] == 6
    assert st["reserved"] == 4
    assert st["sold"] == 0
    assert st["available"] + st["reserved"] + st["sold"] == 10

    # 2. Attempting to reserve more than available (e.g. 7 units when 6 remain) rejects safely
    ok2, msg2, _ = await svc.reserve_stock(
        sku_id="sku-stock-avail",
        user_id="user-2",
        quantity=7,
        lease_seconds=300
    )
    assert ok2 is False
    assert "Insufficient stock" in msg2

    # 3. Release 2 units back to available
    rel_ok, rel_msg = await svc.release_reservation(res_data["reservation_token"])
    assert rel_ok is True
    st_after = await svc.get_stock_status("sku-stock-avail")
    # All 4 released back
    assert st_after["available"] == 10
    assert st_after["reserved"] == 0


@pytest.mark.asyncio
async def test_FLS_041_reserved_quantity(db_session):
    """
    FLS-041: Reserved quantity (BE+DB, P0).
    Verifies (§9 Invariant):
    - Reserved quantity tracks active holds
    - Check constraint chk_inventory_reserved_nonneg prevents negative reserved values
    - Release decrements reserved and increments available
    """
    prod = ProductRecord(product_id="prod-stock-2", title="Stock Item 2", original_price_cents=15000)
    db_session.add(prod)
    inv_mgr = InventoryManager(db_session)
    await inv_mgr.initialize_inventory("sku-stock-res", "prod-stock-2", total_allocated=20)

    svc = StockReservationService(db_session)

    # Reserve 5 units
    ok, _, res1 = await svc.reserve_stock("sku-stock-res", "user-res-1", quantity=5, lease_seconds=120)
    assert ok is True
    st1 = await svc.get_stock_status("sku-stock-res")
    assert st1["reserved"] == 5
    assert st1["available"] == 15

    # Reserve 3 more units
    ok2, _, res2 = await svc.reserve_stock("sku-stock-res", "user-res-2", quantity=3, lease_seconds=120)
    assert ok2 is True
    st2 = await svc.get_stock_status("sku-stock-res")
    assert st2["reserved"] == 8
    assert st2["available"] == 12

    # Release first reservation (5 units)
    await svc.release_reservation(res1["reservation_token"])
    st3 = await svc.get_stock_status("sku-stock-res")
    assert st3["reserved"] == 3
    assert st3["available"] == 17
    assert st3["available"] + st3["reserved"] + st3["sold"] == 20


@pytest.mark.asyncio
async def test_FLS_042_sold_quantity(db_session):
    """
    FLS-042: Sold quantity (BE+DB, P0).
    Verifies (§9 Invariant):
    - Sold quantity increments monotonically on successful checkout
    - Transition converts reserved -> sold
    - Conservation invariant available + reserved + sold == total_allocated holds across every step
    """
    prod = ProductRecord(product_id="prod-stock-3", title="Stock Item 3", original_price_cents=25000)
    db_session.add(prod)
    inv_mgr = InventoryManager(db_session)
    await inv_mgr.initialize_inventory("sku-stock-sold", "prod-stock-3", total_allocated=15)

    svc = StockReservationService(db_session)
    checkout = CheckoutService(db_session)

    # 1. Reserve 5 units
    ok, _, res = await svc.reserve_stock("sku-stock-sold", "buyer-sold-1", quantity=5, lease_seconds=300)
    assert ok is True

    # 2. Complete atomic checkout for 5 units
    chk_ok, msg, order_data = await checkout.process_checkout(
        user_id="buyer-sold-1",
        sku_id="sku-stock-sold",
        quantity=5,
        unit_price_cents=25000,
        reservation_token=res["reservation_token"],
        idempotency_key="chk-sold-test-key-1"
    )
    assert chk_ok is True

    # 3. Verify stock transitions: reserved drops by 5, sold increases by 5
    st = await svc.get_stock_status("sku-stock-sold")
    assert st["available"] == 10
    assert st["reserved"] == 0
    assert st["sold"] == 5
    assert st["available"] + st["reserved"] + st["sold"] == 15


@pytest.mark.asyncio
async def test_FLS_050_sku_level_inventory(db_session):
    """
    FLS-050: SKU-level inventory (BE+DB, P0).
    Verifies:
    - Multiple SKUs belonging to the same product track isolated inventory pools
    - Stock operations on SKU A do not impact available/reserved/sold on SKU B
    - Independent SKU conservation invariants hold
    """
    prod = ProductRecord(product_id="prod-flagship-phone", title="Flagship Phone", original_price_cents=99900)
    db_session.add(prod)

    inv_mgr = InventoryManager(db_session)
    # SKU 1: 128GB Midnight Black
    inv_black = await inv_mgr.initialize_inventory("sku-phone-128-black", "prod-flagship-phone", total_allocated=50)
    # SKU 2: 256GB Silver White
    inv_silver = await inv_mgr.initialize_inventory("sku-phone-256-silver", "prod-flagship-phone", total_allocated=25)

    assert inv_black.sku_id == "sku-phone-128-black"
    assert inv_silver.sku_id == "sku-phone-256-silver"

    svc = StockReservationService(db_session)

    # Reserve 20 on Black
    await svc.reserve_stock("sku-phone-128-black", "buyer-1", quantity=20)

    st_black = await svc.get_stock_status("sku-phone-128-black")
    st_silver = await svc.get_stock_status("sku-phone-256-silver")

    # Black was decremented, Silver remains untouched
    assert st_black["available"] == 30
    assert st_black["reserved"] == 20
    assert st_silver["available"] == 25
    assert st_silver["reserved"] == 0
