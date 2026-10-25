import os

root_dir = "/Users/avishjain/avishjain9-repos/18-flash-sale-inventory"
docs_dir = os.path.join(root_dir, "docs")
features_dir = os.path.join(docs_dir, "features")
os.makedirs(features_dir, exist_ok=True)

def generate_features():
    print("Generating 01-features.md and individual feature deep dives...")

    # 01-features.md
    with open(os.path.join(docs_dir, "01-features.md"), "w") as f:
        f.write("""# Feature Inventory & Architectural Traces

This catalog documents the 12 core architectural feature groups implemented in `18-flash-sale-inventory`, covering all 92 features defined in `FEATURES.csv`.

---

## Feature Matrix Summary

| Feature ID | Feature Name | Primary Source Files | Invariant / Guarantee | Priority |
| :--- | :--- | :--- | :--- | :--- |
| **F1** | Atomic Inventory Reservation | `stock/reservation.py` | Single-query conditional decrement; zero oversell ($A \ge 0$). | P0 |
| **F2** | Virtual Waiting Room Queue | `flow/waiting_room.py` | FIFO token bucket admission; cryptographic ticket verification. | P0 |
| **F3** | Hold Expiration & Rollback | `stock/reservation.py`, `flow/checkout.py` | 300-second hold lease TTL; automatic stock recycling on timeout. | P0 |
| **F4** | Real-Time Oversell Detector | `observability/oversell.py` | Continuous mathematical invariant audit ($A + R + S == T$). | P0 |
| **F5** | Live Storefront & Telemetry | `frontend/src/app.js` | Real-time DOM telemetry, sell-through gauges, instant reservation modal. | P1 |
| **F6** | Distributed Locks with Fencing | `transactions/distributed_lock.py` | Monotonic fencing tokens; stale write rejection. | P0 |
| **F7** | Optimistic Concurrency Control | `transactions/optimistic.py` | Version column matching with bounded exponential backoff retries. | P0 |
| **F8** | Pricing & Promotions Engine | `pricing/pricing.py`, `pricing/promotions.py` | Original price preservation, price floor validation, stacking rules. | P1 |
| **F9** | Scheduled Activation & Timezones | `sales/activation.py` | <= 1.0s activation tolerance; DST boundary crossing handling. | P0 |
| **F10** | Auth, Lockout & Sessions | `auth/service.py`, `models/users.py` | PBKDF2 hashing, exponential cool-down lockout, session token rotation. | P1 |
| **F11** | Payment Resilience & Refunds | `flow/order_payments.py` | Idempotent payment retry, capped refunds, order cancellation. | P0 |
| **F12** | Request Throttling & Quotas | `flow/throttling.py` | Token bucket rate limiting, burst smoothing, per-SKU user limits. | P0 |

---

## Detailed Feature Group Navigation
1. [F1: Atomic Inventory Reservation Engine](./features/F1-atomic-inventory-reservation.md)
2. [F2: Virtual Waiting Room & Traffic Leveling](./features/F2-virtual-waiting-room.md)
3. [F3: Automated Hold Expiration & Stock Rollback](./features/F3-hold-expiration-rollback.md)
4. [F4: Real-time Oversell Audit Detector](./features/F4-oversell-audit-detector.md)
5. [F5: Live Storefront & Operations Console](./features/F5-live-checkout-ui.md)
6. [F6: Distributed Locks with Monotonic Fencing](./features/F6-distributed-locking-fencing.md)
7. [F7: Optimistic Concurrency Control (OCC)](./features/F7-optimistic-concurrency.md)
8. [F8: Pricing, Promotions & Stacking Rules](./features/F8-pricing-promotions-engine.md)
9. [F9: Timezone-Aware Scheduled Activation](./features/F9-scheduled-activation-timezone.md)
10. [F10: Authentication, Exponential Lockout & Session Management](./features/F10-auth-lockout-sessions.md)
11. [F11: Order Lifecycle, Idempotent Payments & Refunds](./features/F11-payment-resilience-refunds.md)
12. [F12: Request Throttling, Burst Smoothing & Quota Enforcement](./features/F12-request-throttling-limits.md)
""")

    # F1
    with open(os.path.join(features_dir, "F1-atomic-inventory-reservation.md"), "w") as f:
        f.write("""# F1: Atomic Inventory Reservation Engine

## Technical Overview
The Atomic Inventory Reservation Engine (`stock/reservation.py`) guarantees zero overselling under high concurrency by executing stock deduction as a single atomic conditional database operation. Instead of the naive "read-then-write" pattern, the engine issues `UPDATE inventory SET available = available - :qty, reserved = reserved + :qty WHERE sku_id = :sku AND available >= :qty`.

```mermaid
flowchart TD
    Client[Shopper Request] --> API[POST /api/v1/reservations]
    API --> Lock[Per-SKU Async Lock]
    Lock --> SQL[Atomic Conditional SQL Update]
    SQL --> Check{Rows Updated == 1?}
    Check -->|Yes| InsertHold[Insert Reservation Record with 300s TTL]
    InsertHold --> ReturnOK[200 OK + Token]
    Check -->|No| Reject[Rollback & Return 409 Conflict]
```

### Trace & Implementation
- **Source Files**: `backend/src/stock/reservation.py:56-120`, `backend/src/api/app.py:72-93`
- **Key Class**: `StockReservationService`
- **Key Method**: `reserve_stock(sku_id, user_id, quantity=1, lease_seconds=300)`
- **Data Touched**: `inventory` table (`available`, `reserved`, `updated_at`), `reservations` table.
- **API Endpoint**: `POST /api/v1/reservations`

### Invariant & Mathematical Proof
The database schema (`models/inventory.py:32-37`) defines:
$$\\text{chk\\_inventory\\_conservation}: available + reserved + sold == total\\_allocated$$
$$\\text{chk\\_inventory\\_available\\_nonneg}: available \\ge 0$$
Because the decrement is guarded by `available >= quantity` within an atomic transaction, $available$ can never drop below zero regardless of thread count.

### Sequence Diagram
```mermaid
sequenceDiagram
    autonumber
    actor Shopper
    participant API as api/app.py
    participant Svc as stock/reservation.py
    participant DB as PostgreSQL 16

    Shopper->>API: POST /api/v1/reservations {sku_id: "sku_sneaker_01", quantity: 1}
    API->>Svc: reserve_stock(sku_id, user_id, 1, 300)
    Svc->>DB: UPDATE inventory SET available = available - 1, reserved = reserved + 1 WHERE sku_id = 'sku_sneaker_01' AND available >= 1
    alt Stock Available
        DB-->>Svc: RowCount = 1
        Svc->>DB: INSERT INTO reservations (token, sku_id, user_id, status='PENDING', expires_at=now+300s)
        DB-->>Svc: Commit OK
        Svc-->>API: (True, "Reservation created", {token: "tok_4a8"})
        API-->>Shopper: 200 OK {reservation_token: "tok_4a8", lease_seconds: 300}
    else Sold Out / Out of Stock
        DB-->>Svc: RowCount = 0
        Svc-->>API: (False, "Insufficient stock", None)
        API-->>Shopper: 409 Conflict {detail: "Insufficient stock or SKU not found"}
    end
```

### Failure Path Diagram
```mermaid
flowchart LR
    Request --> Validate{Valid Payload?}
    Validate -->|No| Err400[400 Bad Request]
    Validate -->|Yes| LockAcquire{Acquire Lock?}
    LockAcquire -->|Timeout| Err503[503 Service Unavailable]
    LockAcquire -->|Success| ExecSQL{Execute Atomic SQL}
    ExecSQL -->|Deadlock| Retry[OCC Retry Loop]
    ExecSQL -->|Rowcount 0| Err409[409 Out of Stock]
    ExecSQL -->|Rowcount 1| PersistHold{Persist Hold?}
    PersistHold -->|DB Crash| Rollback[Transaction Rollback]
    PersistHold -->|Success| Success[200 OK + Token]
```

### Say It Out Loud
> "I built the atomic inventory reservation engine in `src/stock/reservation.py` to completely eliminate overselling during flash-sale stampedes.
>
> In flash sales, traditional e-commerce backends crash because multiple threads read positive stock at the exact same time and then write blind decrements, resulting in negative inventory.
>
> When a buyer clicks reserve, the request hits `POST /api/v1/reservations`. The reservation service executes an atomic conditional update: `UPDATE inventory SET available = available - quantity, reserved = reserved + quantity WHERE sku_id = :sku AND available >= quantity`.
>
> Because this check and update happen in a single atomic SQL operation, the database engine enforces strict mutual exclusion. If the row count is zero, it means the item is completely sold out, and we immediately return a 409 Conflict without creating orphan records.
>
> If the row count is one, we insert a persistent reservation record with a 300-second lease timestamp and return the reservation token to the frontend.
>
> I chose this atomic conditional decrement pattern over distributed Redis Lua scripts for primary durability because PostgreSQL 16 table check constraints guarantee that $available + reserved + sold == total\_allocated$ is enforced by the database kernel itself.
>
> The main limitation is database write lock contention on a single SKU row at extreme scale, which I mitigate by placing the Virtual Waiting Room in front of it."
""")

    # F2
    with open(os.path.join(features_dir, "F2-virtual-waiting-room.md"), "w") as f:
        f.write("""# F2: Virtual Waiting Room & Traffic Leveling

## Technical Overview
The Virtual Waiting Room (`flow/waiting_room.py`) regulates traffic surges during flash-sale openings. When 50,000 users arrive simultaneously, the waiting room enqueues shoppers into a FIFO waiting queue, issues verifiable admission tickets, and meters entry into the checkout flow in controlled batches matching downstream gateway capacity.

```mermaid
flowchart TD
    Shoppers[Surge of 50,000 Users] --> WR[Waiting Room Gatekeeper]
    WR --> FIFO[(In-Memory FIFO Queue)]
    FIFO --> Poller[Client Polling / SSE]
    Admin[Batch Admission Worker] -->|Admit 500 every 5s| FIFO
    FIFO -->|Issue Admission Token| Checkout[Downstream Checkout Services]
```

### Trace & Implementation
- **Source Files**: `backend/src/flow/waiting_room.py:36-150`, `backend/src/api/app.py:558-581`
- **Key Class**: `WaitingRoomManager`
- **Key Methods**: `join_queue(user_id, sku_id)`, `get_ticket_status(user_id, sku_id)`, `admit_batch(sku_id, batch_size, lease_seconds)`
- **API Endpoints**: `POST /api/v1/queue/join`, `GET /api/v1/queue/status`, `POST /api/v1/queue/admit`

### Sequence Diagram
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as frontend/src/app.js
    participant API as api/app.py
    participant WR as flow/waiting_room.py

    User->>UI: Lands on Flash Sale Page
    UI->>API: POST /api/v1/queue/join {user_id: "usr_10", sku_id: "sku_shoe"}
    API->>WR: join_queue("usr_10", "sku_shoe")
    WR-->>API: {ticket_id: "tkt_81a", status: "QUEUED", position: 142}
    API-->>UI: 200 OK + Position 142

    loop Polling Status
        UI->>API: GET /api/v1/queue/status?user_id=usr_10&sku_id=sku_shoe
        API->>WR: get_ticket_status("usr_10", "sku_shoe")
        WR-->>API: {status: "QUEUED", position: 84}
        API-->>UI: Update Estimated Wait: 8 Seconds
    end

    Note over WR: Batch Admission Worker executes admit_batch(sku_id, 100, 120)
    UI->>API: GET /api/v1/queue/status?user_id=usr_10&sku_id=sku_shoe
    API->>WR: get_ticket_status("usr_10", "sku_shoe")
    WR-->>API: {status: "ADMITTED", admission_token: "adm_9b2", expires_at: 1719200720}
    API-->>UI: 200 OK + Admission Token (Redirect to Checkout)
```

### Say It Out Loud
> "I built the Virtual Waiting Room in `src/flow/waiting_room.py` to prevent our checkout database and payment APIs from collapsing under sudden traffic spikes.
>
> When thousands of shoppers rush to buy a product at the exact second a flash sale starts, allowing all of them to hit checkout simultaneously causes connection pool starvation and timeouts.
>
> In my architecture, incoming shoppers call `POST /api/v1/queue/join` and are placed in a FIFO queue. The system returns an admission ticket with their position and estimated wait time.
>
> The frontend polls the status endpoint every two seconds. On the backend, a background admission scheduler calls `admit_batch()`, which admits a controlled batch of 500 users every 5 seconds, issuing them a cryptographically signed admission token with a 120-second lease.
>
> Only shoppers holding an active admission token are permitted to call the reservation and checkout endpoints.
>
> I chose this virtual waiting room architecture over aggressive HTTP 429 rate limiting because dropping user requests creates a terrible customer experience. A waiting room preserves fairness, keeps buyers informed with live countdowns, and levels the load on downstream infrastructure.
>
> One limitation in the current deployment is that the queue state is held in-memory within the FastAPI process; in a multi-node cluster, I would back the queue with Redis Sorted Sets."
""")

    # F3
    with open(os.path.join(features_dir, "F3-hold-expiration-rollback.md"), "w") as f:
        f.write("""# F3: Automated Hold Expiration & Stock Rollback

## Technical Overview
When a customer reserves stock, inventory is shifted from `available` to `reserved` with a 300-second TTL (`models/inventory.py:47`). If payment confirmation is not completed before the TTL expires, the hold is marked `EXPIRED`, and the reserved units are atomically rolled back to `available` stock.

```mermaid
stateDiagram-v2
    [*] --> PENDING: User reserves stock (300s TTL)
    PENDING --> CONFIRMED: Payment succeeds
    CONFIRMED --> [*]: Order fulfilled
    PENDING --> EXPIRED: 300s TTL expires
    EXPIRED --> RELEASED: Rollback worker restores available stock
    RELEASED --> [*]: Stock recycled
```

### Trace & Implementation
- **Source Files**: `backend/src/stock/reservation.py:122-180`, `backend/src/flow/checkout.py:84-110`
- **Key Functions**: `release_reservation()`, `cleanup_expired_reservations()`
- **Data Touched**: `reservations.status = 'EXPIRED'`, `inventory.reserved -= qty`, `inventory.available += qty`

### Say It Out Loud
> "I implemented automated hold expiration and stock rollback to prevent inventory hoarding and abandoned cart lockups.
>
> When a buyer reserves an item, we give them a 300-second window to complete checkout. If the buyer closes their browser or their credit card fails, we cannot leave those items locked forever.
>
> Our checkout service checks the reservation expiration timestamp against the clock before processing payment. If the lease has expired, the checkout request is rejected.
>
> Concurrently, our background reconciliation worker scans for pending reservations where `expires_at < now`. It atomically transitions the reservation status to `EXPIRED` and issues an update to decrement `reserved` stock and increment `available` stock by the exact reservation quantity.
>
> This guarantees that abandoned inventory is automatically recycled back to the sale pool for other shoppers, maintaining 100% stock utilization."
""")

    # F4
    with open(os.path.join(features_dir, "F4-oversell-audit-detector.md"), "w") as f:
        f.write("""# F4: Real-time Oversell Audit Detector

## Technical Overview
The Oversell Audit Detector (`observability/oversell.py`) is an autonomous background consistency auditor that continuously scans all inventory records to verify the mathematical conservation invariant:
$$\\text{Total Allocated} == \\text{Available} + \\text{Reserved} + \\text{Sold}$$

If any discrepancy is detected—or if `available < 0` or `sold > total_allocated`—an `OversellIncident` is created, a Prometheus metric `oversell_incidents_total` is incremented, and a high-severity structured alert is logged.

```mermaid
flowchart TD
    Scanner[Periodic Audit Job] --> ReadDB[Query Inventory Record]
    ReadDB --> Compute[Compute sum = available + reserved + sold]
    Compute --> Check{sum == total_allocated AND available >= 0?}
    Check -->|Yes| InSync[Status: HEALTHY]
    Check -->|No| Alert[Trigger CRITICAL OversellIncident]
    Alert --> Metric[Increment Prometheus Gauge]
    Alert --> Log[Structured JSON Security Log]
```

### Trace & Implementation
- **Source Files**: `backend/src/observability/oversell.py:31-106`, `backend/src/api/app.py:593-616`
- **Key Class**: `OversellDetector`
- **Key Methods**: `audit_sku(session, sku_id)`, `audit_all_inventory(session)`
- **API Endpoints**: `POST /api/v1/incidents/audit`, `GET /api/v1/incidents/oversell`

### Say It Out Loud
> "I built the Real-Time Oversell Detector in `src/observability/oversell.py` to act as an active consistency monitor over our stock ledger.
>
> In financial and inventory systems, database check constraints are essential, but you also need automated runtime telemetry to detect data drift caused by edge cases or split-brain partitions.
>
> My oversell detector performs continuous table audits across all active SKUs. For each record, it verifies that the sum of available, reserved, and sold quantities strictly equals total allocated stock.
>
> If an invariant anomaly or negative stock count is detected, it logs an immutable incident with the discrepancy delta, publishes a Prometheus metric to alert our on-call team, and allows instant query via `GET /api/v1/incidents/oversell`.
>
> This ensures that if any drift ever occurs, it is detected and isolated within seconds."
""")

    # F5
    with open(os.path.join(features_dir, "F5-live-checkout-ui.md"), "w") as f:
        f.write("""# F5: Live Storefront & Operations Console

## Technical Overview
The Storefront & Operations Console (`frontend/src/`) is built with responsive HTML5, CSS3, and modern JavaScript (`app.js`). It connects to the FastAPI backend on port 8180 to provide:
1. Live inventory progress meters displaying percentage sell-through.
2. Real-time status badges (`IN STOCK`, `LOW STOCK`, `SOLD OUT`).
3. An instant checkout reservation modal with real-time countdown timer.
4. Auto-refreshing telemetry polling every 3 seconds.

```mermaid
flowchart LR
    Browser[Client Browser] -->|Polling /api/v1/dashboard/stock| API[FastAPI Gateway]
    API --> DB[(SQLAlchemy DB)]
    DB --> API
    API -->|JSON Stock Telemetry| Browser
    Browser -->|Update DOM Meters & Counters| UI[Dashboard View]
```

### Trace & Implementation
- **Source Files**: `frontend/src/app.js:18-120`, `frontend/src/index.html:40-150`, `frontend/src/index.css:1-180`
- **Key Functions**: `fetchInventoryFeed()`, `renderDashboard()`, `simulateReservation()`
- **Tests**: `frontend/tests/test_dashboard_monitoring.py`, `frontend/tests/test_live_stock_dashboard.py`

### Say It Out Loud
> "I built the live storefront and operations dashboard in vanilla JavaScript and CSS to provide real-time visibility into inventory velocity and sale performance.
>
> The frontend polls the `/api/v1/dashboard/stock` endpoint every three seconds. As reservations and checkouts occur, the UI recalculates total allocated, available, reserved, and sold units, dynamically updating progress meters and sell-through percentages.
>
> When inventory for a SKU drops below 20%, the badge automatically shifts from 'IN STOCK' to 'LOW STOCK' amber, and turns red when sold out.
>
> The interface also includes an interactive checkout modal that lets users simulate instant reservations, starting a live 300-second reservation hold countdown timer directly in the browser."
""")

    # F6
    with open(os.path.join(features_dir, "F6-distributed-locking-fencing.md"), "w") as f:
        f.write("""# F6: Distributed Locks with Monotonic Fencing Tokens

## Technical Overview
The Distributed Lock Manager (`transactions/distributed_lock.py`) guarantees mutual exclusion for critical sections while eliminating the classic distributed locking hazard: **stale writes caused by GC pauses or network delays**. It does this by issuing a monotonically increasing **fencing token** with every lock acquisition.

```mermaid
sequenceDiagram
    autonumber
    participant Client1 as Client 1 (Stale)
    participant LockMgr as DistributedLockManager
    participant Client2 as Client 2 (Active)
    participant Storage as Guarded Resource

    Client1->>LockMgr: acquire("sku_01") -> LockHandle (Token: 1)
    Note over Client1: Long GC Pause (Lock Expires)
    Client2->>LockMgr: acquire("sku_01") -> LockHandle (Token: 2)
    Client2->>Storage: Write with Fencing Token 2 (Accepted)
    Client1->>Storage: Write with Fencing Token 1 (REJECTED: Stale Token 1 < 2)
```

### Trace & Implementation
- **Source Files**: `backend/src/transactions/distributed_lock.py:34-130`
- **Key Class**: `DistributedLockManager`
- **Key Methods**: `acquire(resource_id, owner_id, ttl_seconds)`, `renew(handle)`, `release(handle)`
- **Exception**: `StaleLockFencingError`

### Say It Out Loud
> "I implemented distributed locking with monotonic fencing tokens in `src/transactions/distributed_lock.py` to prevent race conditions during inventory allocation.
>
> In distributed systems, simple locks are dangerous because a client might acquire a lock, experience a long garbage collection pause or network delay, lose the lock when its lease expires, and then wake up and execute a stale write that corrupts the database.
>
> To solve this Martin Kleppmann locking problem, my lock manager increments a monotonic fencing token every time a lock is acquired. When a worker writes to the resource, it must pass this fencing token.
>
> If a worker attempts to write using an older fencing token than the highest one already recorded, the write is immediately rejected with a `StaleLockFencingError`.
>
> This guarantees that even with network partitions or pause pauses, split-brain writes can never corrupt stock counts."
""")

    # F7
    with open(os.path.join(features_dir, "F7-optimistic-concurrency.md"), "w") as f:
        f.write("""# F7: Optimistic Concurrency Control (OCC)

## Technical Overview
Optimistic Concurrency Control (`transactions/optimistic.py`) provides conflict resolution without locking database rows upfront. Every inventory record contains an incrementing `version` column. Updates verify that the version in the database matches the version read initially:
`UPDATE inventory SET available = :new_avail, version = version + 1 WHERE sku_id = :sku AND version = :cur_version`
If another transaction updated the row concurrently, the update returns a row count of 0, triggering an automatic retry with bounded exponential backoff.

```mermaid
flowchart TD
    Start[Read Record & Version v] --> Compute[Calculate New Stock]
    Compute --> Attempt[UPDATE WHERE sku_id = :sku AND version = v]
    Attempt --> Check{Rowcount == 1?}
    Check -->|Yes| Success[Commit & Return]
    Check -->|No| RetryCheck{Attempt < Max Retries?}
    RetryCheck -->|Yes| Sleep[Exponential Backoff Delay] --> Start
    RetryCheck -->|No| Fail[Raise OptimisticConcurrencyError]
```

### Trace & Implementation
- **Source Files**: `backend/src/transactions/optimistic.py:23-88`
- **Key Function**: `update_inventory_optimistic(session, sku_id, quantity, max_retries=5, backoff=0.01)`
- **Exception**: `OptimisticConcurrencyError`

### Say It Out Loud
> "I implemented Optimistic Concurrency Control in `src/transactions/optimistic.py` to handle concurrent stock updates without locking rows.
>
> Instead of using `SELECT FOR UPDATE` which forces concurrent database requests to block and wait in queues, OCC reads the inventory record along with its `version` integer.
>
> When applying the reservation, the update query conditions on that exact version: `WHERE sku_id = :sku AND version = :version`. If another thread modified the row in the meantime, the version check fails and zero rows are updated.
>
> When a conflict occurs, the transaction rolls back cleanly, waits with exponential backoff, and retries up to 5 times.
>
> This guarantees zero lost updates while delivering significantly higher throughput under low to moderate contention."
""")

    # F8
    with open(os.path.join(features_dir, "F8-pricing-promotions-engine.md"), "w") as f:
        f.write("""# F8: Pricing, Promotions & Stacking Rules

## Technical Overview
The Pricing Engine (`pricing/pricing.py`, `pricing/promotions.py`) computes dynamic flash-sale prices while strictly enforcing business guardrails:
1. **Original Price Preservation**: Baseline catalog price is always preserved.
2. **Price Floor Validation**: Effective price can never drop below a hard floor (e.g. wholesale cost).
3. **Maximum Discount Cap**: Total promotional discount is capped at a strict maximum percentage (e.g. 90%).
4. **Promotion Stacking Rules**: Prevents unapproved coupon and promotional stacking under concurrency.

### Trace & Implementation
- **Source Files**: `backend/src/pricing/pricing.py:11-100`, `backend/src/pricing/promotions.py:34-110`
- **Key Classes**: `PricingEngine`, `CouponManager`
- **Key Functions**: `resolve_price()`, `apply_fixed_discount()`, `validate_price_floor()`

### Say It Out Loud
> "I built the pricing and promotion engine in `src/pricing/pricing.py` to ensure that flash-sale discounts never lead to negative margins or revenue leaks.
>
> When a campaign is active, our pricing engine calculates the promotional price in integer cents, avoiding floating-point rounding errors.
>
> It enforces three strict safety checks: first, the final sale price is validated against a minimum price floor so products are never sold below cost; second, maximum discount caps prevent runaway promotional compounding; and third, atomic coupon redemption ensures coupons cannot be double-used under concurrent requests."
""")

    # F9
    with open(os.path.join(features_dir, "F9-scheduled-activation-timezone.md"), "w") as f:
        f.write("""# F9: Timezone-Aware Scheduled Activation

## Technical Overview
The Scheduled Activation Engine (`sales/activation.py`) manages the lifecycle transition of flash-sale campaigns from `SCHEDULED` to `ACTIVE`. It guarantees:
1. **Documented Tolerance**: Activation occurs within $\\le 1.0$ second of the target timestamp.
2. **Timezone & DST Robustness**: Converts IANA wall-clock times to UTC and correctly handles Daylight Saving Time boundary transitions.

### Trace & Implementation
- **Source Files**: `backend/src/sales/activation.py:22-120`
- **Key Classes**: `TimezoneConversionService`, `ScheduledActivationEngine`
- **Key Constant**: `ACTIVATION_TOLERANCE_SECONDS = 1.0`

### Say It Out Loud
> "I built the scheduled activation engine in `src/sales/activation.py` to ensure flash sales launch at the exact millisecond planned, regardless of timezone or Daylight Saving Time shifts.
>
> All campaign start and end times are stored internally in UTC. The service uses Python's `zoneinfo` to convert localized wall-clock inputs into UTC, explicitly verifying whether intervals cross DST shift boundaries.
>
> A background evaluation worker queries scheduled campaigns and activates those due within a tight 1.0-second tolerance window, updating campaign status to `ACTIVE` so product listings instantly reflect flash-sale pricing."
""")

    # F10
    with open(os.path.join(features_dir, "F10-auth-lockout-sessions.md"), "w") as f:
        f.write("""# F10: Authentication, Exponential Lockout & Session Management

## Technical Overview
The Authentication & Session Service (`auth/service.py`) provides secure user authentication, session lifecycle management, and bot protection:
1. **Password Security**: Uses PBKDF2-HMAC-SHA256 with 100,000 iterations and unique cryptographic salts.
2. **Account Lockout**: Triggers account lockout after 5 consecutive failed attempts, scaling exponentially ($15\\text{ min} \\times 2^{\\text{lockouts}}$).
3. **Session Rotation**: Issues unique bearer session tokens with rotation and immediate revocation capabilities.
4. **Per-User Limits**: Enforces strict maximum item quotas per user account (`models/users.py:90-120`).

### Trace & Implementation
- **Source Files**: `backend/src/auth/service.py:67-280`, `backend/src/models/users.py:24-95`
- **Key Classes**: `AuthService`, `SessionManager`, `UserLimitManager`, `BlockedUserRuleManager`
- **API Endpoints**: `/api/v1/auth/register`, `/api/v1/auth/login`, `/api/v1/auth/rotate`, `/api/v1/auth/logout`

### Say It Out Loud
> "I built the authentication and session management subsystem in `src/auth/service.py` to protect flash sales from automated brute-force attacks and credential stuffing.
>
> User passwords are encrypted with PBKDF2-HMAC-SHA256 using 100,000 rounds and a 16-byte cryptographic salt.
>
> If an attacker fails login 5 consecutive times, the account enters exponential cool-down lockout, locking for 15 minutes on the first offense and doubling for subsequent offenses.
>
> For active sessions, the service generates high-entropy bearer tokens, supporting seamless session rotation and instant logout revocation, while strictly enforcing per-user item purchase quotas."
""")

    # F11
    with open(os.path.join(features_dir, "F11-payment-resilience-refunds.md"), "w") as f:
        f.write("""# F11: Order Lifecycle, Idempotent Payments & Refunds

## Technical Overview
The Order & Payment Service (`flow/order_payments.py`) enforces strict transactional integrity across order states and external payment gateways:
1. **Legal State Machine**: Enforces valid transitions via `OrderStateMachine` (`PENDING -> PAID -> REFUNDED`).
2. **Idempotent Payment Retries**: Guarantees that retrying a payment with the same idempotency key never charges the customer twice.
3. **Refund Limits**: Enforces that refund amounts cannot exceed the original captured payment.
4. **Order Cancellation**: Automatically restores inventory when an order is cancelled or payment fails.

### Trace & Implementation
- **Source Files**: `backend/src/flow/order_payments.py:25-240`, `backend/src/models/orders.py:21-46`
- **Key Classes**: `OrderPaymentService`, `OrderStateMachine`
- **Key Methods**: `retry_payment_idempotent()`, `initiate_refund()`, `cancel_order_with_stock_release()`

### Say It Out Loud
> "I built the order lifecycle and payment resilience service in `src/flow/order_payments.py` to prevent double-charging and order state corruption.
>
> All order transitions are governed by a deterministic table-driven state machine. Once an order is marked `PAID`, it can only transition to `REFUNDED`; illegal transitions are rejected at runtime.
>
> When submitting payment, each request carries a unique idempotency key. If a network blip occurs and the user clicks pay again, our service detects the existing payment key and returns the confirmed transaction immediately without touching the payment gateway.
>
> If an order is cancelled, the service automatically releases reserved stock back to the inventory pool."
""")

    # F12
    with open(os.path.join(features_dir, "F12-request-throttling-limits.md"), "w") as f:
        f.write("""# F12: Request Throttling, Burst Smoothing & Quota Enforcement

## Technical Overview
The Throttling Engine (`flow/throttling.py`) protects the gateway from Denial of Service (DoS) and unfair client hoarding using a **Token Bucket Algorithm**:
1. **Smooth Refill**: Refills tokens at a constant rate (e.g. 20 tokens/sec).
2. **Burst Capacity**: Allows short-term bursts up to a configurable maximum (e.g. 50 tokens).
3. **Per-SKU Quotas**: Prevents scalpers from exceeding purchase limits across multiple orders.

### Trace & Implementation
- **Source Files**: `backend/src/flow/throttling.py:23-110`
- **Key Classes**: `TokenBucketThrottler`, `PerSkuPurchaseLimiter`
- **Key Methods**: `acquire(client_id, tokens_requested)`, `assert_within_sku_limit(user_id, sku_id)`

### Say It Out Loud
> "I implemented request throttling and burst smoothing in `src/flow/throttling.py` using a Token Bucket rate limiter.
>
> The token bucket refills continuously at 20 tokens per second with a burst capacity of 50 tokens. This allows legitimate shoppers to burst through checkout steps smoothly while throttling malicious automated bots.
>
> If a client exceeds their allowance, the throttler returns `False` along with the exact fractional seconds to wait before retrying, ensuring fair and predictable access for all shoppers."
""")

    print("Feature documentation generation complete.")

if __name__ == "__main__":
    generate_features()
