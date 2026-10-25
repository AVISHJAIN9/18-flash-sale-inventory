"""
Distributed Locks with Monotonic Fencing Tokens (FLS-010).
Guarantees mutually exclusive resource locking with fencing token generation
and rejection of stale writes (§9 Invariant).
"""

import time
from typing import Dict, Optional, Tuple
from dataclasses import dataclass


class StaleLockFencingError(Exception):
    """Raised when a client attempts a write with an expired or superseded fencing token."""
    pass


class LockAcquisitionError(Exception):
    """Raised when failing to acquire an already-held lock."""
    pass


@dataclass
class LockHandle:
    resource_id: str
    owner_id: str
    fencing_token: int
    expires_at: float

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class DistributedLockManager:
    """
    In-memory / distributed lock manager with monotonically increasing fencing tokens.
    Guarantees:
    - Mutually exclusive lock acquisition per resource_id.
    - Automatic expiry and renewal support.
    - Monotonically increasing fencing tokens to reject stale writes (§9 Invariant).
    """

    def __init__(self):
        # Maps resource_id -> current LockHandle
        self._active_locks: Dict[str, LockHandle] = {}
        # Maps resource_id -> highest fencing token issued
        self._fencing_counters: Dict[str, int] = {}

    def acquire(
        self,
        resource_id: str,
        owner_id: str,
        ttl_seconds: float = 10.0,
        now: Optional[float] = None
    ) -> LockHandle:
        current_time = now if now is not None else time.time()
        existing = self._active_locks.get(resource_id)

        # Check if held and not yet expired
        if existing and current_time <= existing.expires_at and existing.owner_id != owner_id:
            raise LockAcquisitionError(
                f"Resource '{resource_id}' is currently locked by owner '{existing.owner_id}' "
                f"until {existing.expires_at}"
            )

        # Advance monotonic fencing token
        token = self._fencing_counters.get(resource_id, 0) + 1
        self._fencing_counters[resource_id] = token

        handle = LockHandle(
            resource_id=resource_id,
            owner_id=owner_id,
            fencing_token=token,
            expires_at=current_time + ttl_seconds
        )
        self._active_locks[resource_id] = handle
        return handle

    def renew(
        self,
        handle: LockHandle,
        additional_ttl_seconds: float = 10.0,
        now: Optional[float] = None
    ) -> bool:
        current_time = now if now is not None else time.time()
        active = self._active_locks.get(handle.resource_id)
        if not active:
            return False

        # Only current active handle with matching fencing token can renew
        if active.owner_id == handle.owner_id and active.fencing_token == handle.fencing_token:
            active.expires_at = current_time + additional_ttl_seconds
            handle.expires_at = active.expires_at
            return True
        return False

    def release(self, handle: LockHandle) -> bool:
        active = self._active_locks.get(handle.resource_id)
        if not active:
            return False

        if active.owner_id == handle.owner_id and active.fencing_token == handle.fencing_token:
            del self._active_locks[handle.resource_id]
            return True
        return False

    def assert_valid_fencing(
        self,
        resource_id: str,
        fencing_token: int,
        now: Optional[float] = None
    ) -> None:
        """
        Validates fencing token before allowing writes (§9 Invariant).
        Rejects stale writes if fencing token is superseded or expired.
        """
        current_time = now if now is not None else time.time()
        latest_token = self._fencing_counters.get(resource_id, 0)

        if fencing_token < latest_token:
            raise StaleLockFencingError(
                f"Stale fencing token {fencing_token} for resource '{resource_id}'. "
                f"Latest active fencing token is {latest_token}."
            )

        active = self._active_locks.get(resource_id)
        if not active or active.fencing_token != fencing_token or current_time > active.expires_at:
            raise StaleLockFencingError(
                f"Fencing token {fencing_token} is no longer active for resource '{resource_id}'."
            )


default_lock_manager = DistributedLockManager()
