import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.exc import IntegrityError
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager, InventoryRecord

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
async def test_FLS_002_inventory_database(async_session):
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-item-1", title="Console", original_price_cents=49900))

    inv_mgr = InventoryManager(async_session)

    # Initialize 100 units of SKU
    inv = await inv_mgr.initialize_inventory(sku_id="sku-console-blk", product_id="prod-item-1", total_allocated=100)
    assert inv.sku_id == "sku-console-blk"
    assert inv.total_allocated == 100
    assert inv.available == 100
    assert inv.reserved == 0
    assert inv.sold == 0

    # Fetch inventory
    fetched = await inv_mgr.get_inventory("sku-console-blk")
    assert fetched is not None
    assert fetched.available == 100

    # Check conservation invariant: available + reserved + sold == total_allocated
    assert fetched.available + fetched.reserved + fetched.sold == fetched.total_allocated

    # Invariant violation attempt: directly injecting record violating conservation check
    with pytest.raises((IntegrityError, Exception)):
        bad_inv = InventoryRecord(
            sku_id="sku-corrupted",
            product_id="prod-item-1",
            total_allocated=100,
            available=50,
            reserved=10,
            sold=10  # Sum is 70 != 100
        )
        async_session.add(bad_inv)
        await async_session.commit()
