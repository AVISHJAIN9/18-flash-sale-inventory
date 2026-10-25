"""
User Database & Authentication Models (FLS-008).
Provides persistent user schema with password hashing, account status, and lockout tracking.
"""

import enum
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import Column, String, Integer, DateTime, Enum as SQLEnum, Index, ForeignKey
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import Base


class UserStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    LOCKED = "LOCKED"
    SUSPENDED = "SUSPENDED"


class User(Base):
    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    salt = Column(String(64), nullable=False)
    status = Column(SQLEnum(UserStatus), default=UserStatus.ACTIVE, nullable=False)
    failed_login_attempts = Column(Integer, default=0, nullable=False)
    lockout_count = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    def is_locked(self, now: Optional[datetime] = None) -> bool:
        if self.status == UserStatus.LOCKED:
            if self.locked_until:
                current_time = now or datetime.now(timezone.utc)
                if current_time.tzinfo is None:
                    current_time = current_time.replace(tzinfo=timezone.utc)
                locked_dt = self.locked_until
                if locked_dt.tzinfo is None:
                    locked_dt = locked_dt.replace(tzinfo=timezone.utc)
                if current_time < locked_dt:
                    return True
            else:
                return True
        return False


class UserSession(Base):
    __tablename__ = "user_sessions"

    session_id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=False, index=True)
    session_token = Column(String(128), unique=True, nullable=False, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    is_revoked = Column(Integer, default=0, nullable=False)  # 0 = active, 1 = revoked
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def is_valid(self, now: Optional[datetime] = None) -> bool:
        if self.is_revoked == 1:
            return False
        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        exp = self.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        return current_time < exp



def hash_password(password: str, salt: Optional[str] = None) -> tuple[str, str]:
    """Hashes password using PBKDF2-HMAC-SHA256."""
    salt = salt or secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return key.hex(), salt


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    h, _ = hash_password(password, salt)
    return secrets.compare_digest(h, expected_hash)


async def create_user(
    session: AsyncSession,
    username: str,
    email: str,
    password: str,
    status: UserStatus = UserStatus.ACTIVE
) -> User:
    pwd_hash, salt = hash_password(password)
    user_id = f"usr-{secrets.token_hex(8)}"
    user = User(
        id=user_id,
        username=username.strip().lower(),
        email=email.strip().lower(),
        password_hash=pwd_hash,
        salt=salt,
        status=status,
        failed_login_attempts=0
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    return result.scalars().first()


async def get_user_by_username(session: AsyncSession, username: str) -> Optional[User]:
    stmt = select(User).where(User.username == username.strip().lower())
    result = await session.execute(stmt)
    return result.scalars().first()


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    stmt = select(User).where(User.email == email.strip().lower())
    result = await session.execute(stmt)
    return result.scalars().first()
