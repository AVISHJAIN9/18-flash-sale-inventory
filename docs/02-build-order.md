# Step-by-Step Build Order

This guide documents how to rebuild `18-flash-sale-inventory` from scratch in 10 logical phases, detailing the rationale and key code snippets for each phase.

---

## Phase 1: Database Foundation & Invariant Constraints
**Goal**: Create persistent schemas with strict mathematical check constraints.

1. Create `src/db/database.py` with an async SQLAlchemy engine:
```python
# src/db/database.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

DATABASE_URL = "sqlite+aiosqlite:///./flash_sale.db"
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()
```
2. Define `InventoryRecord` in `src/models/inventory.py` with SQL `CheckConstraint`:
```python
# src/models/inventory.py
__table_args__ = (
    CheckConstraint("available >= 0", name="chk_inventory_available_nonneg"),
    CheckConstraint("reserved >= 0", name="chk_inventory_reserved_nonneg"),
    CheckConstraint("sold >= 0", name="chk_inventory_sold_nonneg"),
    CheckConstraint("available + reserved + sold == total_allocated", name="chk_inventory_conservation"),
)
```
*Rationale*: If the database enforces non-negativity and conservation at the kernel level, application bugs can never create phantom stock.

---

## Phase 2: Atomic Stock Reservation Service
**Goal**: Implement single-statement conditional decrements and in-memory SKU locks.

1. Implement `StockReservationService.reserve_stock()` in `src/stock/reservation.py`:
```python
# src/stock/reservation.py
stmt = (
    update(InventoryRecord)
    .where(InventoryRecord.sku_id == sku_id)
    .where(InventoryRecord.available >= quantity)
    .values(
        available=InventoryRecord.available - quantity,
        reserved=InventoryRecord.reserved + quantity,
        updated_at=datetime.now(timezone.utc)
    )
)
res = await self.session.execute(stmt)
if res.rowcount == 0:
    return False, "Insufficient stock", None
```
*Rationale*: Executes availability checking and deduction atomically. Eliminates read-modify-write race conditions.

---

## Phase 3: Virtual Waiting Room & Queue Regulation
**Goal**: Level burst traffic before it hits checkout.

1. Create `WaitingRoomManager` in `src/flow/waiting_room.py`.
2. Implement FIFO queueing with `join_queue()` and metered batch admission with `admit_batch()`.
3. Issue cryptographically verifiable admission tokens with 120-second lease times.

---

## Phase 4: Two-Phase Checkout & Idempotency Engine
**Goal**: Ensure one idempotency key equals at most one order and charge.

1. Build `CheckoutService.process_checkout()` in `src/flow/checkout.py`.
2. Check existing order by `idempotency_key` and return cached order if found.
3. Validate reservation token, verify user ownership, and check lease expiry (`expires_at > now`).
4. Atomically transition reservation to `CONFIRMED`, increment `sold`, and persist `OrderRecord`.

---

## Phase 5: Distributed Locking with Monotonic Fencing
**Goal**: Eliminate Martin Kleppmann stale-write hazards.

1. Create `DistributedLockManager` in `src/transactions/distributed_lock.py`.
2. Issue monotonically increasing fencing tokens on each lock acquisition.
3. Reject writes where client fencing token is less than the highest recorded token.

---

## Phase 6: Timezone-Aware Scheduled Activation
**Goal**: Launch flash sales within a tight 1.0s tolerance window across DST boundaries.

1. Implement `TimezoneConversionService` in `src/sales/activation.py`.
2. Use Python `zoneinfo` to convert wall-clock strings to UTC.
3. Check `is_dst_boundary_crossing()` to guarantee exact scheduling.

---

## Phase 7: Pricing, Promotions & Stacking Engine
**Goal**: Apply discounts while guaranteeing price floors and caps.

1. Implement `PricingEngine` in `src/pricing/pricing.py`.
2. Calculate discounts in integer minor cents (avoid floating-point drift).
3. Validate `price >= price_floor_cents` and `discount <= max_discount_cap`.

---

## Phase 8: Authentication, Session Rotation & Lockout
**Goal**: Secure accounts with PBKDF2 hashing and exponential cool-down.

1. Implement `AuthService` in `src/auth/service.py` using `hashlib.pbkdf2_hmac("sha256", ...)`.
2. Implement exponential lockout: $15 \times 2^{\text{lockouts}}$ minutes after 5 consecutive failed attempts.
3. Support session token rotation and instant revocation.

---

## Phase 9: Observability, Metrics & Invariant Scanners
**Goal**: Real-time alerts and telemetry.

1. Instrument Prometheus gauges in `src/observability/metrics.py`.
2. Implement `OversellDetector` in `src/observability/oversell.py` to audit all SKU rows for drift.
3. Expose `/metrics` endpoint in `src/api/app.py`.

---

## Phase 10: Storefront UI & Live Dashboard
**Goal**: Responsive client interface with live counters and modals.

1. Build `frontend/src/index.html` with stock table, telemetry counters, and checkout modal.
2. Build `frontend/src/app.js` with auto-polling every 3s, sell-through calculators, and status badges.
