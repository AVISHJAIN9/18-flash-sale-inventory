import pytest
import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from stock.reservation import StockReservationService

from sqlalchemy.pool import StaticPool

@pytest_asyncio.fixture
async def async_session_factory(tmp_path):
    db_file = tmp_path / "test_oversell.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield session_maker
    await engine.dispose()

@pytest.mark.asyncio
async def test_FLS_047_oversell_prevention_under_concurrency(async_session_factory):
    # Setup SKU with exactly 10 units
    async with async_session_factory() as session:
        p_mgr = ProductManager(session)
        await p_mgr.create_product(ProductSchema(product_id="prod-stampede", title="Stampede Item", original_price_cents=10000))
        inv_mgr = InventoryManager(session)
        await inv_mgr.initialize_inventory("sku-stampede", "prod-stampede", total_allocated=10)

    # 50 buyers attempt to reserve 1 unit each concurrently
    success_count = 0
    failure_count = 0

    async def attempt_buyer(user_idx: int):
        nonlocal success_count, failure_count
        async with async_session_factory() as session:
            service = StockReservationService(session)
            ok, msg, data = await service.reserve_stock("sku-stampede", f"buyer-{user_idx}", quantity=1)
            if ok:
                success_count += 1
            else:
                failure_count += 1

    # Execute all 50 buyer tasks concurrently
    tasks = [attempt_buyer(i) for i in range(50)]
    await asyncio.gather(*tasks)

    # Verify results:
    # Exactly 10 successes, exactly 40 rejections, 0 oversell!
    assert success_count == 10
    assert failure_count == 40

    # Verify inventory state: available == 0, reserved == 10, total == 10
    async with async_session_factory() as session:
        service = StockReservationService(session)
        st = await service.get_stock_status("sku-stampede")
        assert st["available"] == 0
        assert st["reserved"] == 10
        assert st["total_allocated"] == 10
