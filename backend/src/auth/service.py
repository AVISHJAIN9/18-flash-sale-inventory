"""
Authentication, Session Management, Account Lockout, and User Policy Service.
Features:
- FLS-026: User authentication
- FLS-032: Per-user limits
- FLS-036: Blocked-user rules
- FLS-037: Account lockout with exponential cool-down
- FLS-038: Session management with rotation and revocation
"""

import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Tuple, Set
import logging
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from models.users import (
    User, UserStatus, UserSession,
    hash_password, verify_password,
    get_user_by_username, get_user_by_email, get_user_by_id
)
from models.orders import OrderRecord, OrderStatus
from models.inventory import ReservationRecord, ReservationStatus

logger = logging.getLogger("auth.service")

MAX_FAILED_ATTEMPTS = 5
BASE_LOCKOUT_MINUTES = 15.0


class AuthException(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class InvalidCredentialsError(AuthException):
    def __init__(self, message: str = "Invalid username/email or password"):
        super().__init__("INVALID_CREDENTIALS", message)


class UserBlockedError(AuthException):
    def __init__(self, message: str = "User account has been blocked due to policy violations"):
        super().__init__("ACCOUNT_BLOCKED", message)


class AccountLockedError(AuthException):
    def __init__(self, message: str, locked_until: Optional[datetime] = None):
        super().__init__("ACCOUNT_LOCKED", message)
        self.locked_until = locked_until


class PerUserLimitExceededError(AuthException):
    def __init__(self, message: str, current_quantity: int, requested_quantity: int, limit: int):
        super().__init__("PER_USER_LIMIT_EXCEEDED", message)
        self.current_quantity = current_quantity
        self.requested_quantity = requested_quantity
        self.limit = limit


class InvalidSessionError(AuthException):
    def __init__(self, message: str = "Session token is invalid, expired, or revoked"):
        super().__init__("INVALID_SESSION", message)


class BlockedUserRuleManager:
    """
    Evaluates blocked user rules (FLS-036).
    Rejects blocked status, banned domains, or malicious account flags.
    """
    def __init__(self, banned_domains: Optional[Set[str]] = None):
        self.banned_domains = banned_domains or {"trashmail.com", "fraud-bot.net"}

    def is_blocked(self, user: User) -> Tuple[bool, Optional[str]]:
        if user.status == UserStatus.BLOCKED:
            return True, f"User '{user.id}' is explicitly marked BLOCKED"
        domain = user.email.split("@")[-1].lower() if "@" in user.email else ""
        if domain in self.banned_domains:
            return True, f"User email domain '@{domain}' matches blocked-domain rule"
        return False, None

    def assert_not_blocked(self, user: User) -> None:
        blocked, reason = self.is_blocked(user)
        if blocked:
            raise UserBlockedError(reason or "User account is blocked")


class UserLimitManager:
    """
    Tracks and enforces per-user SKU purchase limits under concurrency (FLS-032).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_user_allocated_quantity(self, user_id: str, sku_id: str) -> int:
        """
        Calculates cumulative active reservations + paid/pending orders for this user on this SKU.
        """
        # 1. Orders
        order_stmt = (
            select(func.coalesce(func.sum(OrderRecord.quantity), 0))
            .where(OrderRecord.user_id == user_id)
            .where(OrderRecord.sku_id == sku_id)
            .where(OrderRecord.status.in_([OrderStatus.PENDING.value, OrderStatus.PAID.value]))
        )
        order_qty = await self.session.scalar(order_stmt) or 0

        # 2. Active reservations
        res_stmt = (
            select(func.coalesce(func.sum(ReservationRecord.quantity), 0))
            .where(ReservationRecord.user_id == user_id)
            .where(ReservationRecord.sku_id == sku_id)
            .where(ReservationRecord.status == ReservationStatus.PENDING.value)
        )
        res_qty = await self.session.scalar(res_stmt) or 0

        return int(order_qty + res_qty)

    async def assert_within_limit(
        self,
        user_id: str,
        sku_id: str,
        requested_quantity: int,
        max_limit: int
    ) -> None:
        current_allocated = await self.get_user_allocated_quantity(user_id, sku_id)
        if current_allocated + requested_quantity > max_limit:
            raise PerUserLimitExceededError(
                f"Requested quantity {requested_quantity} would exceed user limit of {max_limit} (already allocated: {current_allocated})",
                current_quantity=current_allocated,
                requested_quantity=requested_quantity,
                limit=max_limit
            )


class SessionManager:
    """
    Session Token Lifecycle: creation, validation, rotation, and revocation (FLS-038).
    """
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_session(self, user_id: str, ttl_hours: int = 24) -> UserSession:
        token = f"fls_sess_{secrets.token_urlsafe(32)}"
        session_id = f"sess_{secrets.token_hex(8)}"
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=ttl_hours)

        sess_rec = UserSession(
            session_id=session_id,
            user_id=user_id,
            session_token=token,
            expires_at=expires_at,
            is_revoked=0,
            created_at=now
        )
        self.session.add(sess_rec)
        await self.session.commit()
        await self.session.refresh(sess_rec)
        return sess_rec

    async def validate_session(self, token: str, now: Optional[datetime] = None) -> Tuple[User, UserSession]:
        stmt = (
            select(UserSession, User)
            .join(User, UserSession.user_id == User.id)
            .where(UserSession.session_token == token)
        )
        res = await self.session.execute(stmt)
        row = res.first()
        if not row:
            raise InvalidSessionError("Session not found")

        sess_rec, user = row
        if not sess_rec.is_valid(now=now):
            raise InvalidSessionError("Session has expired or been revoked")

        return user, sess_rec

    async def rotate_session(self, old_token: str) -> UserSession:
        """
        Session rotation (§9 Invariant): invalidates the old token and issues a fresh one.
        """
        user, old_sess = await self.validate_session(old_token)
        old_sess.is_revoked = 1

        new_sess = await self.create_session(user_id=user.id)
        await self.session.commit()
        return new_sess

    async def revoke_session(self, token: str) -> bool:
        """
        Revokes an active session (§9 Invariant).
        """
        stmt = select(UserSession).where(UserSession.session_token == token)
        res = await self.session.execute(stmt)
        sess_rec = res.scalars().first()
        if not sess_rec:
            return False
        sess_rec.is_revoked = 1
        await self.session.commit()
        return True


class AuthService:
    """
    User Authentication Service (FLS-026) with Account Lockout (FLS-037).
    """
    def __init__(self, session: AsyncSession):
        self.session = session
        self.rule_mgr = BlockedUserRuleManager()
        self.session_mgr = SessionManager(session)

    async def register(self, username: str, email: str, password: str) -> User:
        existing_u = await get_user_by_username(self.session, username)
        if existing_u:
            raise AuthException("USER_EXISTS", f"Username '{username}' is already registered")

        existing_e = await get_user_by_email(self.session, email)
        if existing_e:
            raise AuthException("EMAIL_EXISTS", f"Email '{email}' is already registered")

        pwd_hash, salt = hash_password(password)
        user_id = f"usr_{secrets.token_hex(8)}"
        user = User(
            id=user_id,
            username=username.strip().lower(),
            email=email.strip().lower(),
            password_hash=pwd_hash,
            salt=salt,
            status=UserStatus.ACTIVE,
            failed_login_attempts=0,
            lockout_count=0
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def authenticate(
        self,
        identifier: str,
        password: str,
        now: Optional[datetime] = None
    ) -> Tuple[User, UserSession]:
        """
        Authenticates user with exponential lockout protection.
        """
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)

        # 1. Lookup user
        user = await get_user_by_username(self.session, identifier)
        if not user:
            user = await get_user_by_email(self.session, identifier)
        if not user:
            raise InvalidCredentialsError()

        # 2. Blocked status check (FLS-036)
        self.rule_mgr.assert_not_blocked(user)

        # 3. Lockout check with exponential cool-down (FLS-037)
        if user.is_locked(now=current_time):
            raise AccountLockedError(
                f"Account is locked until {user.locked_until.isoformat()} due to excessive failed attempts",
                locked_until=user.locked_until
            )

        # If previous lock expired, reset status and failed attempts
        if user.status == UserStatus.LOCKED and not user.is_locked(now=current_time):
            user.status = UserStatus.ACTIVE
            user.failed_login_attempts = 0

        # 4. Verify password
        if not verify_password(password, user.salt, user.password_hash):
            user.failed_login_attempts += 1

            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                # Exponential cool-down (§9 Invariant): base * 2^(lockout_count)
                cool_down_minutes = BASE_LOCKOUT_MINUTES * (2 ** user.lockout_count)
                user.status = UserStatus.LOCKED
                user.locked_until = current_time + timedelta(minutes=cool_down_minutes)
                user.lockout_count += 1
                await self.session.commit()
                raise AccountLockedError(
                    f"Account locked for {cool_down_minutes} minutes due to {user.failed_login_attempts} failed login attempts",
                    locked_until=user.locked_until
                )

            await self.session.commit()
            raise InvalidCredentialsError()

        # 5. Success! Reset failure counters
        user.failed_login_attempts = 0
        user.lockout_count = 0
        user.locked_until = None
        user.status = UserStatus.ACTIVE

        session = await self.session_mgr.create_session(user.id)
        await self.session.commit()
        return user, session
