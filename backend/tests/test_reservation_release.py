import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, ReservationStatus
from stock.reservation import StockReservationService

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
async def test_FLS_046_reservation_release(async_session):
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-rel", title="Microwave", original_price_cents=15000))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-rel", "prod-rel", total_allocated=20)

    service = StockReservationService(async_session)

    # Reserve 5 units
    ok, _, data = await service.reserve_stock("sku-rel", "user-rel-1", quantity=5)
    assert ok is True
    tok = data["reservation_token"]

    st1 = await service.get_stock_status("sku-rel")
    assert st1["available"] == 15
    assert st1["reserved"] == 5

    # Explicit user release
    ok_rel, msg_rel = await service.release_reservation(tok)
    assert ok_rel is True

    # Reserved stock restored to available immediately
    st2 = await service.get_stock_status("sku-rel")
    assert st2["available"] == 20
    assert st2["reserved"] == 0

    # Attempting to release again fails safely
    ok_dup, msg_dup = await service.release_reservation(tok)
    assert ok_dup is False
    assert "Cannot release reservation" in msg_dup
