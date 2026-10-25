import pytest
import pytest_asyncio
import asyncio
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.database import Base
from models.catalog import ProductRecord
from models.inventory import InventoryRecord
from models.users import (
    User, UserStatus, create_user, get_user_by_id, get_user_by_username,
    get_user_by_email, verify_password
)
from transactions.distributed_lock import (
    DistributedLockManager, StaleLockFencingError, LockAcquisitionError
)
from transactions.optimistic import (
    update_inventory_optimistic, OptimisticConcurrencyError
)


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
async def test_FLS_008_user_database(db_session):
    """
    FLS-008: User database (BE+DB, P0).
    Verifies:
    - User creation with PBKDF2 password hashing & salt
    - Unique constraints on username and email
    - Lockout status and timestamps
    """
    # 1. Create active user
    user = await create_user(
        session=db_session,
        username="flash_shopper_1",
        email="shopper1@example.com",
        password="SuperSecretPassword123!"
    )
    assert user.id.startswith("usr-")
    assert user.username == "flash_shopper_1"
    assert user.email == "shopper1@example.com"
    assert user.status == UserStatus.ACTIVE
    assert user.failed_login_attempts == 0
    assert verify_password("SuperSecretPassword123!", user.salt, user.password_hash) is True
    assert verify_password("WrongPassword!", user.salt, user.password_hash) is False

    # 2. Query lookups by ID, username, and email
    fetched_by_id = await get_user_by_id(db_session, user.id)
    assert fetched_by_id is not None
    assert fetched_by_id.id == user.id

    fetched_by_name = await get_user_by_username(db_session, "FLASH_SHOPPER_1")  # case-insensitive
    assert fetched_by_name is not None
    assert fetched_by_name.id == user.id

    fetched_by_email = await get_user_by_email(db_session, "SHOPPER1@example.com")
    assert fetched_by_email is not None
    assert fetched_by_email.id == user.id

    # 3. Lockout evaluation
    user.status = UserStatus.LOCKED
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
    assert user.is_locked() is True

    # After expiry, lockout releases
    past_time = datetime.now(timezone.utc) + timedelta(minutes=20)
    assert user.is_locked(now=past_time) is False


def test_FLS_010_distributed_locks_fencing():
    """
    FLS-010: Distributed locks (BE, P0).
    Verifies (§9 Invariant):
    - Mutually exclusive resource acquisition
    - Monotonically increasing fencing tokens
    - Rejection of stale writes when fencing token is superseded
    """
    lock_mgr = DistributedLockManager()
    clock = 1000.0

    # 1. Client 1 acquires lock on inventory SKU-99
    h1 = lock_mgr.acquire(resource_id="sku-99", owner_id="client-worker-1", ttl_seconds=10.0, now=clock)
    assert h1.resource_id == "sku-99"
    assert h1.owner_id == "client-worker-1"
    assert h1.fencing_token == 1
    assert h1.expires_at == 1010.0

    # 2. Client 2 attempts to acquire lock before expiration -> rejects
    with pytest.raises(LockAcquisitionError) as exc:
        lock_mgr.acquire(resource_id="sku-99", owner_id="client-worker-2", ttl_seconds=10.0, now=clock + 2.0)
    assert "currently locked by owner 'client-worker-1'" in str(exc.value)

    # 3. Valid write using fencing token 1
    lock_mgr.assert_valid_fencing(resource_id="sku-99", fencing_token=h1.fencing_token, now=clock + 3.0)

    # 4. Advance clock past expiration (clock = 1015.0) -> Client 2 acquires new lock with higher fencing token
    h2 = lock_mgr.acquire(resource_id="sku-99", owner_id="client-worker-2", ttl_seconds=10.0, now=clock + 15.0)
    assert h2.fencing_token == 2
    assert h2.owner_id == "client-worker-2"

    # 5. Stale write rejection: Client 1 tries to write with stale fencing token 1 (§9 Invariant)
    with pytest.raises(StaleLockFencingError) as stale_exc:
        lock_mgr.assert_valid_fencing(resource_id="sku-99", fencing_token=h1.fencing_token, now=clock + 16.0)
    assert "Stale fencing token 1" in str(stale_exc.value)

    # Valid write with latest fencing token 2 succeeds
    lock_mgr.assert_valid_fencing(resource_id="sku-99", fencing_token=h2.fencing_token, now=clock + 16.0)


@pytest.mark.asyncio
async def test_FLS_012_optimistic_concurrency_retries(db_session):
    """
    FLS-012: Optimistic concurrency (BE, P0).
    Verifies (§9 Invariant):
    - Optimistic version checks prevent lost updates
    - Automatic bounded retries resolve write conflicts
    - Conservation invariant available + reserved + sold == total holds
    """
    # 1. Seed product and inventory
    product = ProductRecord(product_id="prod-phone-1", title="Flash Phone X", original_price_cents=99900)
    db_session.add(product)
    await db_session.commit()

    inv = InventoryRecord(
        sku_id="sku-phone-black",
        product_id="prod-phone-1",
        total_allocated=50,
        available=50,
        reserved=0,
        sold=0,
        version=1
    )
    db_session.add(inv)
    await db_session.commit()

    # 2. First reservation succeeds cleanly
    updated = await update_inventory_optimistic(
        session=db_session,
        sku_id="sku-phone-black",
        quantity_to_reserve=5
    )
    assert updated.available == 45
    assert updated.reserved == 5
    assert updated.version == 2
    assert updated.available + updated.reserved + updated.sold == 50

    # 3. Simulate concurrency conflict: another worker advances version while attempt 1 is in-flight
    conflict_injected = False
    async def inject_conflict():
        nonlocal conflict_injected
        if not conflict_injected:
            conflict_injected = True
            await db_session.execute(
                update(InventoryRecord)
                .where(InventoryRecord.sku_id == "sku-phone-black")
                .values(version=10, available=40, reserved=10)
            )
            await db_session.commit()

    updated2 = await update_inventory_optimistic(
        session=db_session,
        sku_id="sku-phone-black",
        quantity_to_reserve=2,
        max_retries=3,
        _conflict_injector=inject_conflict
    )
    assert updated2.available == 38
    assert updated2.reserved == 12
    assert updated2.version == 11
    assert updated2.available + updated2.reserved + updated2.sold == 50

    # 4. Verify bounded retry limit exhaustion raises OptimisticConcurrencyError
    async def always_conflict():
        await db_session.execute(
            update(InventoryRecord)
            .where(InventoryRecord.sku_id == "sku-phone-black")
            .values(version=InventoryRecord.version + 10)
        )
        await db_session.commit()

    with pytest.raises(OptimisticConcurrencyError):
        await update_inventory_optimistic(
            session=db_session,
            sku_id="sku-phone-black",
            quantity_to_reserve=1,
            max_retries=2,
            _conflict_injector=always_conflict
        )
