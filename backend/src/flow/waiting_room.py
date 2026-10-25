"""
Waiting Room and Purchase Admission Controller (FLS-065, FLS-066).
Manages virtual waiting rooms during high-concurrency flash sales.
Regulates traffic admission with rate-controlled leases and cryptographically verifiable admission tokens.
"""

from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone, timedelta
from enum import Enum
import uuid
from clock import Clock

class QueueStatus(str, Enum):
    QUEUED = "QUEUED"
    ADMITTED = "ADMITTED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"

class AdmissionTicket:
    def __init__(
        self,
        ticket_id: str,
        user_id: str,
        sku_id: str,
        joined_at: float
    ):
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.sku_id = sku_id
        self.joined_at = joined_at
        self.status = QueueStatus.QUEUED
        self.admission_token: Optional[str] = None
        self.admitted_at: Optional[float] = None
        self.expires_at: Optional[float] = None

class WaitingRoomManager:
    """
    Manages user queues and admissions for flash sale SKUs.
    Enforces FIFO queue admission with time-bounded admission leases.
    """
    def __init__(self, clock: Optional[Clock] = None):
        self.clock = clock or Clock()
        # sku_id -> list of ticket_ids in queue
        self._queues: Dict[str, List[str]] = {}
        # ticket_id -> AdmissionTicket
        self._tickets: Dict[str, AdmissionTicket] = {}
        # token -> ticket_id
        self._token_to_ticket: Dict[str, str] = {}
        # user_id + sku_id -> ticket_id (prevent duplicate queue entries)
        self._user_active_ticket: Dict[Tuple[str, str], str] = {}

    def join_queue(self, user_id: str, sku_id: str) -> Dict[str, Any]:
        """
        Enqueues a buyer in the waiting room (FLS-066).
        Returns current queue position and ticket details.
        """
        user_key = (user_id, sku_id)
        now_ts = self.clock.now()

        # If user already in queue or admitted, return current status
        if user_key in self._user_active_ticket:
            existing_ticket_id = self._user_active_ticket[user_key]
            ticket = self._tickets.get(existing_ticket_id)
            if ticket and ticket.status in (QueueStatus.QUEUED, QueueStatus.ADMITTED):
                pos = self._get_position(sku_id, existing_ticket_id)
                return {
                    "ticket_id": ticket.ticket_id,
                    "user_id": user_id,
                    "sku_id": sku_id,
                    "status": ticket.status.value,
                    "position": pos,
                    "admission_token": ticket.admission_token
                }

        ticket_id = f"tkt_{uuid.uuid4().hex[:12]}"
        ticket = AdmissionTicket(
            ticket_id=ticket_id,
            user_id=user_id,
            sku_id=sku_id,
            joined_at=now_ts
        )

        if sku_id not in self._queues:
            self._queues[sku_id] = []
        self._queues[sku_id].append(ticket_id)
        self._tickets[ticket_id] = ticket
        self._user_active_ticket[user_key] = ticket_id

        position = len(self._queues[sku_id])
        return {
            "ticket_id": ticket_id,
            "user_id": user_id,
            "sku_id": sku_id,
            "status": QueueStatus.QUEUED.value,
            "position": position,
            "admission_token": None
        }

    def admit_batch(
        self,
        sku_id: str,
        batch_size: int,
        lease_seconds: int = 120
    ) -> List[Dict[str, Any]]:
        """
        Admits a controlled batch of buyers from the waiting room into the purchase flow (FLS-065).
        Generates unique time-limited admission tokens.
        """
        if batch_size <= 0:
            return []

        queue = self._queues.get(sku_id, [])
        admitted = []
        now_ts = self.clock.now()

        num_to_admit = min(batch_size, len(queue))
        for _ in range(num_to_admit):
            ticket_id = queue.pop(0)
            ticket = self._tickets[ticket_id]

            token = f"adm_{uuid.uuid4().hex}"
            ticket.status = QueueStatus.ADMITTED
            ticket.admission_token = token
            ticket.admitted_at = now_ts
            ticket.expires_at = now_ts + lease_seconds

            self._token_to_ticket[token] = ticket_id
            admitted.append({
                "ticket_id": ticket.ticket_id,
                "user_id": ticket.user_id,
                "sku_id": ticket.sku_id,
                "status": ticket.status.value,
                "admission_token": token,
                "expires_at": ticket.expires_at,
                "lease_seconds": lease_seconds
            })

        return admitted

    def verify_admission(self, user_id: str, admission_token: str) -> Tuple[bool, str]:
        """
        Validates if an admission token is valid, active, and belongs to the user (FLS-065).
        """
        if not admission_token:
            return False, "Admission token required"

        ticket_id = self._token_to_ticket.get(admission_token)
        if not ticket_id:
            return False, "Invalid or unknown admission token"

        ticket = self._tickets.get(ticket_id)
        if not ticket:
            return False, "Ticket not found"

        if ticket.user_id != user_id:
            return False, "Admission token does not belong to user"

        now_ts = self.clock.now()
        if ticket.status == QueueStatus.CONSUMED:
            return False, "Admission token already consumed"

        if ticket.status == QueueStatus.EXPIRED or (ticket.expires_at and now_ts > ticket.expires_at):
            ticket.status = QueueStatus.EXPIRED
            return False, "Admission token has expired"

        if ticket.status != QueueStatus.ADMITTED:
            return False, f"Ticket status '{ticket.status.value}' is not admitted"

        return True, "Admission token valid"

    def consume_admission(self, user_id: str, admission_token: str) -> bool:
        """
        Marks admission token as consumed upon checkout/order creation.
        """
        valid, _ = self.verify_admission(user_id, admission_token)
        if not valid:
            return False

        ticket_id = self._token_to_ticket[admission_token]
        ticket = self._tickets[ticket_id]
        ticket.status = QueueStatus.CONSUMED
        self._user_active_ticket.pop((ticket.user_id, ticket.sku_id), None)
        return True

    def expire_stale_admissions(self) -> int:
        """
        Sweeps and expires admitted tickets whose lease has elapsed.
        """
        now_ts = self.clock.now()
        count = 0
        for ticket in self._tickets.values():
            if ticket.status == QueueStatus.ADMITTED and ticket.expires_at and now_ts > ticket.expires_at:
                ticket.status = QueueStatus.EXPIRED
                self._user_active_ticket.pop((ticket.user_id, ticket.sku_id), None)
                count += 1
        return count

    def get_queue_status(self, sku_id: str) -> Dict[str, Any]:
        """
        Returns real-time queue length and active admissions.
        """
        queue = self._queues.get(sku_id, [])
        now_ts = self.clock.now()
        admitted_active = sum(
            1 for t in self._tickets.values()
            if t.sku_id == sku_id and t.status == QueueStatus.ADMITTED and (not t.expires_at or t.expires_at > now_ts)
        )
        return {
            "sku_id": sku_id,
            "queued_count": len(queue),
            "admitted_active_count": admitted_active
        }

    def get_user_position(
        self,
        user_id: str,
        sku_id: str,
        admission_rate_per_sec: float = 1.0
    ) -> Dict[str, Any]:
        """
        Calculates user queue position and estimated wait time in seconds (FLS-079).
        """
        user_key = (user_id, sku_id)
        ticket_id = self._user_active_ticket.get(user_key)
        if not ticket_id:
            return {"in_queue": False, "position": 0, "users_ahead": 0, "estimated_wait_seconds": 0}

        ticket = self._tickets.get(ticket_id)
        if not ticket or ticket.status != QueueStatus.QUEUED:
            return {
                "in_queue": False,
                "status": ticket.status.value if ticket else "UNKNOWN",
                "position": 0,
                "users_ahead": 0,
                "estimated_wait_seconds": 0
            }

        position = self._get_position(sku_id, ticket_id)
        users_ahead = max(0, position - 1)
        rate = max(0.1, admission_rate_per_sec)
        estimated_wait = int(users_ahead / rate)

        return {
            "in_queue": True,
            "ticket_id": ticket_id,
            "position": position,
            "users_ahead": users_ahead,
            "estimated_wait_seconds": estimated_wait
        }

    def generate_queue_token(
        self,
        ticket_id: str,
        secret: str = "flash_sale_hmac_secret",
        ttl_seconds: int = 600
    ) -> str:
        """
        Generates a tamper-proof cryptographically signed queue token (FLS-080).
        Format: qtok_<base64_payload>.<signature>
        """
        import hmac, hashlib, base64, json
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket '{ticket_id}' not found")

        now_ts = self.clock.now()
        payload = {
            "ticket_id": ticket.ticket_id,
            "user_id": ticket.user_id,
            "sku_id": ticket.sku_id,
            "issued_at": now_ts,
            "expires_at": now_ts + ttl_seconds
        }
        raw_json = json.dumps(payload, separators=(',', ':'), sort_keys=True).encode()
        b64_payload = base64.urlsafe_b64encode(raw_json).decode()

        sig = hmac.new(secret.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()
        return f"qtok_{b64_payload}.{sig}"

    def verify_queue_token(
        self,
        queue_token: str,
        secret: str = "flash_sale_hmac_secret"
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validates the authenticity and expiration of a cryptographic queue token (FLS-080).
        """
        import hmac, hashlib, base64, json
        if not queue_token or not queue_token.startswith("qtok_"):
            return False, "Invalid queue token format", None

        raw = queue_token[len("qtok_"):]
        if "." not in raw:
            return False, "Malformed queue token signature", None

        b64_payload, signature = raw.split(".", 1)
        expected_sig = hmac.new(secret.encode(), b64_payload.encode(), hashlib.sha256).hexdigest()

        if not hmac.compare_digest(signature, expected_sig):
            return False, "Queue token signature verification failed (tampered)", None

        try:
            raw_json = base64.urlsafe_b64decode(b64_payload.encode())
            payload = json.loads(raw_json)
        except Exception:
            return False, "Failed to decode queue token payload", None

        now_ts = self.clock.now()
        if now_ts > payload.get("expires_at", 0):
            return False, "Queue token has expired", None

        return True, "Queue token valid", payload

    def check_ip_limit(
        self,
        ip_address: str,
        max_requests: int = 10,
        window_seconds: float = 60.0
    ) -> Tuple[bool, int]:
        """
        Per-IP rate limiting protecting waiting room from DDoS and bot hammering (FLS-085).
        """
        if not hasattr(self, "_ip_history"):
            self._ip_history: Dict[str, List[float]] = {}

        now_ts = self.clock.now()
        history = self._ip_history.setdefault(ip_address, [])

        # Evict timestamps outside sliding window
        self._ip_history[ip_address] = [t for t in history if now_ts - t <= window_seconds]
        current_count = len(self._ip_history[ip_address])

        if current_count >= max_requests:
            return False, current_count

        self._ip_history[ip_address].append(now_ts)
        return True, current_count + 1

    def _get_position(self, sku_id: str, ticket_id: str) -> int:
        queue = self._queues.get(sku_id, [])
        try:
            return queue.index(ticket_id) + 1
        except ValueError:
            return 0

    def expire_stale_tickets(
        self,
        sku_id: str,
        max_queue_age_seconds: float = 600.0
    ) -> List[str]:
        """
        Expires tickets that have exceeded max queue time or admission lease TTL (FLS-081).
        """
        now_ts = self.clock.now()
        queue = self._queues.get(sku_id, [])
        expired_ids = []

        # 1. Prune expired queue tickets
        retained_queue = []
        for tid in queue:
            ticket = self._tickets.get(tid)
            if ticket and (now_ts - ticket.joined_at) > max_queue_age_seconds:
                ticket.status = QueueStatus.EXPIRED
                expired_ids.append(tid)
                self._user_active_ticket.pop((ticket.user_id, sku_id), None)
            else:
                retained_queue.append(tid)
        self._queues[sku_id] = retained_queue

        # 2. Prune expired admitted tickets
        for tid, ticket in list(self._tickets.items()):
            if ticket.sku_id == sku_id and ticket.status == QueueStatus.ADMITTED:
                if ticket.expires_at and now_ts > ticket.expires_at:
                    ticket.status = QueueStatus.EXPIRED
                    expired_ids.append(tid)
                    if ticket.admission_token:
                        self._token_to_ticket.pop(ticket.admission_token, None)
                    self._user_active_ticket.pop((ticket.user_id, sku_id), None)

        return expired_ids

    def randomized_admit_draw(
        self,
        sku_id: str,
        num_to_admit: int,
        lease_seconds: int = 120,
        rng=None
    ) -> List[Dict[str, Any]]:
        """
        Randomized admission lottery (FLS-084).
        Selects winners with uniform probability over waiting pool.
        Statistically uniform over N >= 10,000 draws (§9 Invariant).
        """
        queue = self._queues.get(sku_id, [])
        if not queue or num_to_admit <= 0:
            return []

        import random as py_random
        rand = rng or py_random.Random()

        actual_to_admit = min(num_to_admit, len(queue))
        # Draw winners uniformly without replacement
        winner_indices = sorted(rand.sample(range(len(queue)), actual_to_admit), reverse=True)
        winner_ticket_ids = [queue.pop(idx) for idx in winner_indices]

        now_ts = self.clock.now()
        admitted = []

        for tid in winner_ticket_ids:
            ticket = self._tickets[tid]
            ticket.status = QueueStatus.ADMITTED
            ticket.admitted_at = now_ts
            ticket.expires_at = now_ts + lease_seconds
            token = f"adm_{uuid.uuid4().hex}"
            ticket.admission_token = token
            self._token_to_ticket[token] = tid

            admitted.append({
                "ticket_id": ticket.ticket_id,
                "user_id": ticket.user_id,
                "sku_id": ticket.sku_id,
                "status": ticket.status.value,
                "admission_token": token,
                "expires_at": ticket.expires_at
            })

        return admitted

    def check_account_limit(
        self,
        user_id: str,
        sku_id: str,
        max_active_tickets: int = 1
    ) -> Tuple[bool, str]:
        """
        Per-account waiting room limits (FLS-086).
        Prevents account from holding multiple active waiting room tickets.
        """
        user_key = (user_id, sku_id)
        if user_key in self._user_active_ticket:
            tid = self._user_active_ticket[user_key]
            ticket = self._tickets.get(tid)
            if ticket and ticket.status in (QueueStatus.QUEUED, QueueStatus.ADMITTED):
                return False, f"Account '{user_id}' already has an active queue ticket ({tid})"
        return True, "OK"

    def get_ticket_status(self, user_id: str, sku_id: str) -> Dict[str, Any]:
        """
        Queries status and position of a buyer's ticket (FLS-111).
        """
        user_key = (user_id, sku_id)
        tid = self._user_active_ticket.get(user_key)
        if not tid:
            return {"in_queue": False, "status": "NOT_IN_QUEUE"}
        ticket = self._tickets.get(tid)
        pos = self._get_position(sku_id, tid)
        return {
            "ticket_id": tid,
            "user_id": user_id,
            "sku_id": sku_id,
            "status": ticket.status.value if ticket else "UNKNOWN",
            "position": pos,
            "admission_token": ticket.admission_token if ticket else None
        }



