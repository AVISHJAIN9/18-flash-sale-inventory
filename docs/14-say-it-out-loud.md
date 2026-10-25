# Say It Out Loud: Complete Interview Spoken Scripts

This document gathers the spoken interview scripts for every feature in `18-flash-sale-inventory`, formatted in conversational first-person English.

---

## 30-Second Elevator Pitch
> "I built an atomic inventory reservation engine in FastAPI, Redis, and SQLAlchemy that handles massive flash-sale traffic surges without overselling a single unit. It combines a virtual waiting room to regulate queue admission, atomic stock reservations using conditional decrement logic and monotonic fencing tokens to execute inventory holds in under one millisecond, and automated timeout workers that immediately restore abandoned holds to the available pool. The system continuously enforces the mathematical invariant that available plus reserved plus sold inventory strictly equals total stock, backed by 96 automated concurrency and chaos tests."

---

## 2-Minute Technical Interview Pitch
> "During flash-sale events—such as limited sneaker drops or concert ticket releases—tens of thousands of concurrent buyers hit checkout in the exact same millisecond. Traditional relational databases immediately crash due to row lock contention, deadlocks, and connection exhaustion, leading to disastrous overselling and negative stock counts.
>
> To solve this, I designed and built **18-Flash-Sale-Inventory**, an enterprise-grade, zero-oversell inventory reservation platform.
>
> The architecture addresses the three fundamental failure modes of high-throughput commerce:
>
> First, Traffic Smoothing via a Virtual Waiting Room (`src/flow/waiting_room.py`): Instead of letting 50,000 requests slam the checkout database simultaneously, incoming shoppers enter a virtual waiting room. The system issues cryptographically signed admission tickets and regulates downstream entry in metered batches based on downstream payment gateway capacity.
>
> Second, Sub-Millisecond Atomic Stock Reservation (`src/stock/reservation.py`): I decoupled inventory availability checks from heavy database transactions. The reservation service executes an atomic conditional decrement (`UPDATE ... WHERE available >= :q`). We also pair this with in-memory distributed locking with monotonic fencing tokens (`src/transactions/distributed_lock.py`), ensuring that even under extreme concurrency, stock availability checks and temporary 10-minute hold creations execute atomically without stale reads.
>
> Third, Two-Phase Checkout and Automated Stock Rollback (`src/flow/checkout.py`, `src/flow/order_payments.py`): When a buyer reserves an item, a 300-second hold token is issued. If checkout succeeds, payment is captured idempotently and stock is permanently committed to the ledger. If payment fails or the buyer abandons checkout, an asynchronous reconciliation engine automatically expires the hold and replenishes available stock.
>
> The system continuously checks the core invariant: Available + Reserved + Sold == Total Allocated. A background audit engine detects any mathematical drift or negative inventory in real time. The entire engine is verified by 96 automated tests."

---

## Feature 1: Atomic Inventory Reservation Engine
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

---

## Feature 2: Virtual Waiting Room & Queue Regulation
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

---

## Feature 3: Automated Hold Expiration & Rollback
> "I implemented automated hold expiration and stock rollback to prevent inventory hoarding and abandoned cart lockups.
>
> When a buyer reserves an item, we give them a 300-second window to complete checkout. If the buyer closes their browser or their credit card fails, we cannot leave those items locked forever.
>
> Our checkout service checks the reservation expiration timestamp against the clock before processing payment. If the lease has expired, the checkout request is rejected.
>
> Concurrently, our background reconciliation worker scans for pending reservations where `expires_at < now`. It atomically transitions the reservation status to `EXPIRED` and issues an update to decrement `reserved` stock and increment `available` stock by the exact reservation quantity.
>
> This guarantees that abandoned inventory is automatically recycled back to the sale pool for other shoppers, maintaining 100% stock utilization."

---

## Feature 4: Real-time Oversell Audit Detector
> "I built the Real-Time Oversell Detector in `src/observability/oversell.py` to act as an active consistency monitor over our stock ledger.
>
> In financial and inventory systems, database check constraints are essential, but you also need automated runtime telemetry to detect data drift caused by edge cases or split-brain partitions.
>
> My oversell detector performs continuous table audits across all active SKUs. For each record, it verifies that the sum of available, reserved, and sold quantities strictly equals total allocated stock.
>
> If an invariant anomaly or negative stock count is detected, it logs an immutable incident with the discrepancy delta, publishes a Prometheus metric to alert our on-call team, and allows instant query via `GET /api/v1/incidents/oversell`.
>
> This ensures that if any drift ever occurs, it is detected and isolated within seconds."

---

## Rehearsal Checklist
- [ ] Pitch: 30-Second Elevator Pitch recited aloud in under 30 seconds.
- [ ] Pitch: 2-Minute Technical Interview Pitch recited clearly in under 2 minutes.
- [ ] Feature 1: Atomic Inventory Reservation Engine explained smoothly without notes.
- [ ] Feature 2: Virtual Waiting Room & Traffic Leveling explained with queue mechanics.
- [ ] Feature 3: Automated Hold Expiration & Rollback explained with TTL recycling.
- [ ] Feature 4: Real-time Oversell Audit Detector explained with mathematical invariants.
