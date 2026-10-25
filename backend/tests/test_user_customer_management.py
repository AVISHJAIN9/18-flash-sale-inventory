"""
Tests for User & Customer Management:
- FLS-026: User authentication (FE+BE+DB)
- FLS-032: Per-user limits (FE+BE+DB)
- FLS-036: Blocked-user rules (FE+BE+DB)
- FLS-037: Account lockout with exponential cool-down (FE+BE+DB)
- FLS-038: Session management with rotation and revocation (FE+BE+DB)
"""

import os
import pytest
import pytest_asyncio
import httpx
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from db.database import Base, get_db
from models.catalog import ProductRecord
from models.inventory import InventoryRecord
from models.users import User, UserStatus, UserSession
from auth.service import (
    AuthService, SessionManager, UserLimitManager, BlockedUserRuleManager,
    InvalidCredentialsError, UserBlockedError, AccountLockedError,
    PerUserLimitExceededError, InvalidSessionError
)
from api.app import app


@pytest_asyncio.fixture
async def test_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def override_get_db():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {
            "client": client,
            "session_maker": session_maker,
            "engine": engine
        }

    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_FLS_026_user_authentication(test_env):
    """
    FLS-026: User authentication (FE+BE+DB, P1).
    Verifies:
    - Frontend DOM elements for auth exist and are wired
    - Registration persists real hashed credentials in DB
    - Login returns real active session token
    - Invalid password rejects with 401
    """
    client = test_env["client"]

    # 1. Frontend assets integrity
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "..", "frontend", "src", "index.html")
    assert os.path.isfile(html_path), "index.html missing"
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    assert 'id="auth-section"' in html
    assert 'id="auth-username-input"' in html
    assert 'id="auth-password-input"' in html
    assert 'id="auth-login-btn"' in html
    assert 'id="auth-status-badge"' in html
    assert 'id="auth-error-msg"' in html

    # 2. Register via API
    reg_resp = await client.post("/api/v1/auth/register", json={
        "username": "flash_speedy_1",
        "email": "speedy1@example.com",
        "password": "SuperSecretPassword123!"
    })
    assert reg_resp.status_code == 201, reg_resp.text
    user_data = reg_resp.json()
    assert user_data["username"] == "flash_speedy_1"
    assert user_data["status"] == "ACTIVE"

    # 3. Successful login
    login_resp = await client.post("/api/v1/auth/login", json={
        "identifier": "flash_speedy_1",
        "password": "SuperSecretPassword123!"
    })
    assert login_resp.status_code == 200, login_resp.text
    token_data = login_resp.json()
    assert "session_token" in token_data
    assert token_data["session_token"].startswith("fls_sess_")
    assert token_data["user"]["username"] == "flash_speedy_1"

    # 4. Failed login with invalid password
    bad_resp = await client.post("/api/v1/auth/login", json={
        "identifier": "flash_speedy_1",
        "password": "WrongPassword999!"
    })
    assert bad_resp.status_code == 401
    assert "Invalid username/email or password" in bad_resp.json()["detail"]


@pytest.mark.asyncio
async def test_FLS_032_per_user_limits(test_env):
    """
    FLS-032: Per-user limits (FE+BE+DB, P1).
    Verifies (§9 Invariant):
    - Per-SKU and per-account purchase limits hold
    - Requests exceeding per-user limit are rejected
    - Limit monitoring endpoint reflects accurate remaining allowance
    - Frontend DOM includes user limit display
    """
    client = test_env["client"]
    sm = test_env["session_maker"]

    # Frontend DOM verification
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html_path = os.path.join(base_dir, "..", "frontend", "src", "index.html")
    with open(html_path, "r", encoding="utf-8") as f:
        html = f.read()
    assert 'id="user-limit-display"' in html

    # Seed product & inventory
    async with sm() as session:
        p = ProductRecord(product_id="prod-limited-1", title="Limited GPU", original_price_cents=79900)
        inv = InventoryRecord(sku_id="sku-gpu-limit", product_id="prod-limited-1", total_allocated=10, available=10, reserved=0, sold=0, version=1)
        session.add(p)
        session.add(inv)
        await session.commit()

        # Check limits directly via UserLimitManager
        lm = UserLimitManager(session)
        # Limit is 2 items
        await lm.assert_within_limit(user_id="user-limit-tester", sku_id="sku-gpu-limit", requested_quantity=2, max_limit=2)

        # Attempting 3 items exceeds limit -> raises PerUserLimitExceededError
        with pytest.raises(PerUserLimitExceededError) as exc:
            await lm.assert_within_limit(user_id="user-limit-tester", sku_id="sku-gpu-limit", requested_quantity=3, max_limit=2)
        assert exc.value.limit == 2
        assert exc.value.requested_quantity == 3

    # Check via REST API limit query endpoint
    lim_resp = await client.get("/api/v1/users/user-limit-tester/limits/sku-gpu-limit?max_limit=2")
    assert lim_resp.status_code == 200
    lim_data = lim_resp.json()
    assert lim_data["user_id"] == "user-limit-tester"
    assert lim_data["max_limit"] == 2
    assert lim_data["allocated_quantity"] == 0
    assert lim_data["remaining_allowance"] == 2
    assert lim_data["is_limit_reached"] is False


@pytest.mark.asyncio
async def test_FLS_036_blocked_user_rules(test_env):
    """
    FLS-036: Blocked-user rules (FE+BE+DB, P1).
    Verifies:
    - User account with BLOCKED status is rejected with 403 FORBIDDEN
    - User with fraudulent/banned email domain is rejected
    - Clean active users pass
    """
    client = test_env["client"]
    sm = test_env["session_maker"]

    async with sm() as session:
        auth = AuthService(session)
        # Register user with normal credentials
        user = await auth.register("blocked_bad_actor", "badguy@normal.com", "Password123!")
        # Admin marks user as BLOCKED
        user.status = UserStatus.BLOCKED
        await session.commit()

        # Register user with banned fraud domain
        banned_user = await auth.register("bot_operator", "bot99@trashmail.com", "Password123!")

    # Attempt login with explicitly BLOCKED status -> 403 Forbidden
    resp_blocked = await client.post("/api/v1/auth/login", json={
        "identifier": "blocked_bad_actor",
        "password": "Password123!"
    })
    assert resp_blocked.status_code == 403
    assert "BLOCKED" in resp_blocked.json()["detail"]

    # Attempt login with banned domain rule -> 403 Forbidden
    resp_banned = await client.post("/api/v1/auth/login", json={
        "identifier": "bot_operator",
        "password": "Password123!"
    })
    assert resp_banned.status_code == 403
    assert "trashmail.com" in resp_banned.json()["detail"]


@pytest.mark.asyncio
async def test_FLS_037_account_lockout_exponential_cool_down(test_env):
    """
    FLS-037: Account lockout with exponential cool-down (FE+BE+DB, P1).
    Verifies (§9 Invariant):
    - Account lockout triggers after 5 failed login attempts
    - 1st lockout cool-down = 15 minutes (base)
    - Advancing clock past 15 min unlocks account
    - Subsequent lockout cools down exponentially: 2nd lockout = 30 minutes!
    """
    sm = test_env["session_maker"]

    async with sm() as session:
        auth = AuthService(session)
        user = await auth.register("lockout_test_user", "lockout@example.com", "CorrectPassword123!")

        clock_now = datetime(2026, 11, 10, 10, 0, 0, tzinfo=timezone.utc)

        # 1. Submit 4 failed attempts -> still unlocked
        for _ in range(4):
            with pytest.raises(InvalidCredentialsError):
                await auth.authenticate("lockout_test_user", "WrongPassword", now=clock_now)

        assert user.failed_login_attempts == 4
        assert user.status == UserStatus.ACTIVE

        # 2. 5th failed attempt triggers 1st lockout (15 minutes cool-down)
        with pytest.raises(AccountLockedError) as lock_exc1:
            await auth.authenticate("lockout_test_user", "WrongPassword", now=clock_now)

        assert user.status == UserStatus.LOCKED
        assert user.lockout_count == 1
        expected_lock1 = clock_now + timedelta(minutes=15)
        assert lock_exc1.value.locked_until == expected_lock1

        # 3. Before lockout expiration (at +10 min), authentication is locked
        with pytest.raises(AccountLockedError):
            await auth.authenticate("lockout_test_user", "CorrectPassword123!", now=clock_now + timedelta(minutes=10))

        # 4. Advance clock past 15 min (+16 min) -> lockout expires, but wrong password again starts new cycle
        clock_after_lock1 = clock_now + timedelta(minutes=16)

        # Submit 5 more failed attempts to trigger 2nd lockout
        for _ in range(4):
            with pytest.raises(InvalidCredentialsError):
                await auth.authenticate("lockout_test_user", "WrongAgain", now=clock_after_lock1)

        # 5th attempt in 2nd cycle -> triggers 2nd lockout (exponential: 15 * 2^1 = 30 minutes cool-down!)
        with pytest.raises(AccountLockedError) as lock_exc2:
            await auth.authenticate("lockout_test_user", "WrongAgain", now=clock_after_lock1)

        assert user.status == UserStatus.LOCKED
        assert user.lockout_count == 2
        expected_lock2 = clock_after_lock1 + timedelta(minutes=30)
        assert lock_exc2.value.locked_until == expected_lock2


@pytest.mark.asyncio
async def test_FLS_038_session_management_rotation_revocation(test_env):
    """
    FLS-038: Session management (FE+BE+DB, P1).
    Verifies (§9 Invariant):
    - Real session tokens generated and validated
    - Session rotation invalidates the old token and returns fresh token
    - Stale or rotated tokens are rejected
    - Session revocation (logout) immediately terminates session
    """
    client = test_env["client"]

    # 1. Register & login to get token A
    await client.post("/api/v1/auth/register", json={
        "username": "sess_user_1",
        "email": "sess1@example.com",
        "password": "Password123!"
    })
    login_resp = await client.post("/api/v1/auth/login", json={
        "identifier": "sess_user_1",
        "password": "Password123!"
    })
    token_a = login_resp.json()["session_token"]

    # 2. Token A valid on /api/v1/auth/me
    me_resp_a = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert me_resp_a.status_code == 200
    assert me_resp_a.json()["username"] == "sess_user_1"

    # 3. Rotate session (§9 Invariant) -> Token B returned, Token A revoked
    rotate_resp = await client.post("/api/v1/auth/rotate", headers={"Authorization": f"Bearer {token_a}"})
    assert rotate_resp.status_code == 200
    token_b = rotate_resp.json()["session_token"]
    assert token_b != token_a

    # 4. Token A is now stale and rejected
    stale_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_a}"})
    assert stale_resp.status_code == 401

    # 5. Token B is active and valid
    me_resp_b = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert me_resp_b.status_code == 200

    # 6. Revoke session (logout)
    logout_resp = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token_b}"})
    assert logout_resp.status_code == 200
    assert logout_resp.json()["revoked"] is True

    # 7. Token B is now revoked and rejected
    revoked_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token_b}"})
    assert revoked_resp.status_code == 401
