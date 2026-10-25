import pytest
import pytest_asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductManager, ProductSchema
from models.inventory import InventoryManager
from models.campaigns import CampaignManager, CampaignSchema, CampaignStatus

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
async def test_FLS_006_campaign_database(async_session):
    p_mgr = ProductManager(async_session)
    await p_mgr.create_product(ProductSchema(product_id="prod-laptop-1", title="Gaming Laptop", original_price_cents=199900))
    inv_mgr = InventoryManager(async_session)
    await inv_mgr.initialize_inventory("sku-laptop-1", "prod-laptop-1", total_allocated=100)

    camp_mgr = CampaignManager(async_session)
    now = datetime.now(timezone.utc)

    # Create campaign
    c = CampaignSchema(
        campaign_id="camp-flash-1",
        title="Midnight Flash Sale",
        sku_id="sku-laptop-1",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=3),
        sale_price_cents=129900,  # Discounted from 199900
        allocated_stock=50,
        per_user_limit=1,
        status=CampaignStatus.SCHEDULED.value
    )
    created = await camp_mgr.create_campaign(c)
    assert created.campaign_id == "camp-flash-1"
    assert created.sale_price_cents == 129900
    assert created.per_user_limit == 1

    # Fetch campaign
    fetched = await camp_mgr.get_campaign("camp-flash-1")
    assert fetched is not None
    assert fetched.title == "Midnight Flash Sale"

    # Negative test: end_time before start_time
    with pytest.raises(ValueError):
        await camp_mgr.create_campaign(CampaignSchema(
            campaign_id="camp-bad",
            title="Bad",
            sku_id="sku-laptop-1",
            start_time=now + timedelta(hours=5),
            end_time=now + timedelta(hours=2),
            sale_price_cents=1000,
            allocated_stock=10
        ))
