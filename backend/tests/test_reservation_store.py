import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, ReservationStore, ReservationStatus

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
async def test_FLS_003_reservation_store(async_session):
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-tv-1", title="4K OLED TV", original_price_cents=120000))

    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory(sku_id="sku-tv-55", product_id="prod-tv-1", total_allocated=50)

    res_store = ReservationStore(async_session)

    # Create 5-minute reservation
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    res = await res_store.create_reservation(
        reservation_id="res-usr1-001",
        sku_id="sku-tv-55",
        user_id="user-123",
        quantity=1,
        expires_at=expires
    )
    assert res.reservation_id == "res-usr1-001"
    assert res.status == ReservationStatus.PENDING.value
    assert res.quantity == 1

    # Fetch reservation
    fetched = await res_store.get_reservation("res-usr1-001")
    assert fetched is not None
    assert fetched.user_id == "user-123"

    # List user reservations
    user_res = await res_store.list_user_reservations("user-123")
    assert len(user_res) == 1
    assert user_res[0].sku_id == "sku-tv-55"

    # Negative test: quantity must be positive
    with pytest.raises(ValueError):
        await res_store.create_reservation(
            reservation_id="res-bad",
            sku_id="sku-tv-55",
            user_id="user-123",
            quantity=0,
            expires_at=expires
        )
