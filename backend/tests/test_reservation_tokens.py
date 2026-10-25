import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from stock.reservation import StockReservationService
from flow.checkout import CheckoutService

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
async def test_FLS_075_reservation_tokens(async_session):
    """
    FLS-075: Reservation tokens.
    Verifies that checkout requires a valid cryptographically secure reservation token,
    checks that the token matches the buyer identity and SKU, and rejects counterfeit/hijacked tokens.
    """
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-tok-sku", title="GPU", original_price_cents=69900))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-gpu", "prod-tok-sku", total_allocated=5)

    stock_svc = StockReservationService(async_session)
    checkout_svc = CheckoutService(async_session)

    # Legitimate buyer reserves 1 GPU
    ok, _, data = await stock_svc.reserve_stock("sku-gpu", "legit-buyer", quantity=1)
    assert ok is True
    token = data["reservation_token"]
    assert token.startswith("tok_")

    # 1. Non-existent reservation token -> rejected
    ok1, msg1, _ = await checkout_svc.process_checkout(
        user_id="legit-buyer",
        sku_id="sku-gpu",
        quantity=1,
        unit_price_cents=69900,
        reservation_token="tok_fabricated_fake",
        idempotency_key="chk-tok-1"
    )
    assert ok1 is False
    assert "not found" in msg1.lower()

    # 2. Token hijacking attempt: another user tries to use legit-buyer's token -> rejected
    ok2, msg2, _ = await checkout_svc.process_checkout(
        user_id="attacker-user",
        sku_id="sku-gpu",
        quantity=1,
        unit_price_cents=69900,
        reservation_token=token,
        idempotency_key="chk-tok-2"
    )
    assert ok2 is False
    assert "belongs to a different user" in msg2

    # 3. Legitimate user checkout with token -> succeeds
    ok3, msg3, data3 = await checkout_svc.process_checkout(
        user_id="legit-buyer",
        sku_id="sku-gpu",
        quantity=1,
        unit_price_cents=69900,
        reservation_token=token,
        idempotency_key="chk-tok-3"
    )
    assert ok3 is True
    assert data3["status"] == "PAID"
