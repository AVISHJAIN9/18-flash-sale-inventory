# Project Pitch: High-Concurrency Flash Sale Inventory Engine

## 30-Second Elevator Pitch
> "I built **18-Flash-Sale-Inventory**, a high-concurrency reservation engine in FastAPI, Redis, and SQLAlchemy that handles massive flash-sale traffic surges without overselling a single unit. It combines a virtual waiting room to regulate queue admission, atomic stock reservations using conditional decrement logic and monotonic fencing tokens to execute inventory holds in under one millisecond, and automated timeout workers that immediately restore abandoned holds to the available pool. The system continuously enforces the mathematical invariant that available plus reserved plus sold inventory strictly equals total stock, backed by 96 automated concurrency and chaos tests."

---

## 2-Minute Technical Interview Pitch
> "During flash-sale events—such as limited sneaker drops or concert ticket releases—tens of thousands of concurrent buyers hit checkout in the exact same millisecond. Traditional relational databases immediately crash due to row lock contention, deadlocks, and connection exhaustion, leading to disastrous overselling and negative stock counts.
>
> To solve this, I designed and built **18-Flash-Sale-Inventory**, an enterprise-grade, zero-oversell inventory reservation platform.
>
> The architecture addresses the three fundamental failure modes of high-throughput commerce:
>
> **First, Traffic Smoothing via a Virtual Waiting Room (`src/flow/waiting_room.py`)**:
> Instead of letting 50,000 requests slam the checkout database simultaneously, incoming shoppers enter a virtual waiting room. The system issues cryptographically signed admission tickets and regulates downstream entry in metered batches based on payment gateway capacity.
>
> **Second, Sub-Millisecond Atomic Stock Reservation (`src/stock/reservation.py`)**:
> I decoupled inventory availability checks from heavy database transactions. The reservation service executes an atomic conditional decrement (`UPDATE ... WHERE available >= :q`). We also pair this with in-memory distributed locking with monotonic fencing tokens (`src/transactions/distributed_lock.py`), ensuring that even under extreme concurrency, stock availability checks and temporary 10-minute hold creations execute atomically without stale reads.
>
> **Third, Two-Phase Checkout and Automated Stock Rollback (`src/flow/checkout.py`, `src/flow/order_payments.py`)**:
> When a buyer reserves an item, a 300-second hold token is issued. If checkout succeeds, payment is captured idempotently and stock is permanently committed to the ledger. If payment fails or the buyer abandons checkout, an asynchronous reconciliation engine automatically expires the hold and replenishes available stock.
>
> **Observability and Invariant Verification (`src/observability/oversell.py`)**:
> The system continuously checks the core invariant: **Available + Reserved + Sold == Total Allocated**. A background audit engine detects any mathematical drift or negative inventory in real time.
>
> The entire engine is covered by 96 automated tests, including multi-threaded race condition tests, chaos cache dropouts, and timezone-aware DST flash-sale activations."
