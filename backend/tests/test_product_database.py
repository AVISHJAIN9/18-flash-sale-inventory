import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema

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
async def test_FLS_001_product_database(async_session):
    mgr = ProductManager(async_session)

    # 1. Create valid product (price in integer cents: $99.99 -> 9999)
    p = ProductSchema(
        product_id="prod-phone-1",
        title="Flagship Smartphone 256GB",
        description="High-end smartphone with OLED screen",
        original_price_cents=99999
    )
    created = await mgr.create_product(p)
    assert created.product_id == "prod-phone-1"
    assert created.original_price_cents == 99999

    # 2. Get product
    fetched = await mgr.get_product("prod-phone-1")
    assert fetched is not None
    assert fetched.title == "Flagship Smartphone 256GB"

    # 3. List products
    products = await mgr.list_products()
    assert len(products) == 1

    # 4. Negative test: Negative price rejected
    with pytest.raises(ValueError):
        await mgr.create_product(ProductSchema(
            product_id="bad-prod",
            title="Bad",
            original_price_cents=-500
        ))

    # 5. Negative test: Empty title rejected
    with pytest.raises(ValueError):
        await mgr.create_product(ProductSchema(
            product_id="bad-title",
            title="   ",
            original_price_cents=1000
        ))
