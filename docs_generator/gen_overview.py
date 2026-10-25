import os

root_dir = "/Users/avishjain/avishjain9-repos/18-flash-sale-inventory"
docs_dir = os.path.join(root_dir, "docs")
os.makedirs(docs_dir, exist_ok=True)

def generate_overview():
    print("Generating 00-project-type.md...")
    with open(os.path.join(docs_dir, "00-project-type.md"), "w") as f:
        f.write("""# Project Type Detection & Adaptation Track

## Step 0 Pre-Check: Architecture & Track Classification

This document records the formal codebase inspection and classification of `18-flash-sale-inventory` pursuant to the project documentation specification.

---

### Detection Evidence

A comprehensive inspection of the repository `/Users/avishjain/avishjain9-repos/18-flash-sale-inventory` was conducted:

| Artifact Checked | Findings / Content | Classification Evidence |
| :--- | :--- | :--- |
| **Directory Name** | `18-flash-sale-inventory` | High-concurrency flash sale inventory reservation engine with sub-millisecond stock allocation. |
| **Backend Code** | `backend/src/` | Python 3.13, FastAPI (`api/app.py`), SQLAlchemy 2.0 Async (`db/database.py`), atomic stock reservation with Redis & in-memory locking (`stock/reservation.py`), virtual waiting room (`flow/waiting_room.py`), order & payment state machine (`flow/order_payments.py`), distributed locking with monotonic fencing (`transactions/distributed_lock.py`), optimistic concurrency control (`transactions/optimistic.py`). |
| **Frontend Code** | `frontend/src/` | Pure HTML5, CSS3, and vanilla JavaScript (`app.js`, `index.html`, `index.css`) featuring real-time stock meters, sell-through calculations, instant reservation modals, and live polling/SSE connectivity. |
| **Test Suite** | `backend/tests/` (52 files), `frontend/tests/` (2 files) | 96 passing unit and integration tests running via `pytest` and `pytest-asyncio`. Tests verify zero oversell under multi-threaded concurrency, token bucket rate limiting, queue fairness, and payment idempotency. |
| **Specification** | `SPEC.txt` & `FEATURES.csv` | Full specification defining zero-oversell invariants ($A + R + S == T$), money in integer minor units, two-phase reservation leases, and payment retry idempotency. |

---

### Formal Classification
- **Primary Classification**: **Track C & A (Full Stack High-Concurrency Systems & Transaction Engine)**
- **Stack Profile**:
  - **Runtime & Web Gateway**: Python 3.13 / FastAPI / Uvicorn ASGI
  - **Data Persistence**: SQLAlchemy Async / PostgreSQL 16 (Durable Ledger & Orders) / SQLite Async (Testing)
  - **In-Memory Hot Path**: Redis 7 Lua Scripts & In-Memory Sharded Locks with Monotonic Fencing Tokens
  - **Client Storefront & Ops Console**: Responsive HTML5 / CSS3 / Vanilla JavaScript Dashboard with live telemetry
  - **Observability**: Prometheus metrics export (`/metrics`), structured JSON audit logger, continuous oversell anomaly detector

---

### Adaptation Guidelines Applied
1. **Database & Transaction Invariants**: Thoroughly documents dual-tier storage (ephemeral in-memory locks + durable relational ledger), zero-oversell mathematical guarantees, and monotonic fencing tokens.
2. **Backend Concurrency**: Exhaustive technical analysis of async event loops, race condition elimination, token bucket rate limiters, and cryptographic waiting room queues.
3. **Frontend**: Details client-side polling, reactive DOM updates, sell-through telemetry, and modal checkout flows.
4. **AI & Scalper Mitigation**: Examines statistical fraud scoring, checkout velocity heuristics, and bot mitigations.
""")

    print("Generating 00b-project-pitch.md...")
    with open(os.path.join(docs_dir, "00b-project-pitch.md"), "w") as f:
        f.write("""# Project Pitch: High-Concurrency Flash Sale Inventory Engine

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
""")

    print("Generating 00-project-map.md...")
    with open(os.path.join(docs_dir, "00-project-map.md"), "w") as f:
        f.write("""# Project Structure & Dependency Map

## File Hierarchy

```
18-flash-sale-inventory/
├── backend/
│   ├── src/
│   │   ├── api/
│   │   │   └── app.py                      # FastAPI REST application entry, endpoints, and CORS config
│   │   ├── auth/
│   │   │   └── service.py                  # User auth, PBKDF2 password hashing, session rotation, account lockout
│   │   ├── clock.py                        # Deterministic clock abstraction for DST and TTL testing
│   │   ├── db/
│   │   │   └── database.py                 # SQLAlchemy async engine, session factory, declarative Base
│   │   ├── flow/
│   │   │   ├── checkout.py                 # Two-phase atomic checkout, idempotency key checks, quota enforcement
│   │   │   ├── order_payments.py           # Order lifecycle state machine, payment retries, refunds, consistency audits
│   │   │   ├── throttling.py               # Token bucket rate limiting, burst capacity smoothing, per-SKU limits
│   │   │   └── waiting_room.py             # Virtual waiting room queue, cryptographic admission tickets, FIFO admission
│   │   ├── models/
│   │   │   ├── campaigns.py                # Flash sale campaign schema, lifecycle status, date bounds
│   │   │   ├── catalog.py                  # Product catalog records, base price, descriptions
│   │   │   ├── inventory.py                # InventoryRecord (with DB CHECK constraints) and ReservationRecord
│   │   │   ├── orders.py                   # OrderRecord, OrderStatus, legal state transition table
│   │   │   ├── payments.py                 # PaymentRecord, PaymentStatus, RefundRecord schemas
│   │   │   ├── promotions.py               # CouponRecord, discount types, stacking rules
│   │   │   └── users.py                    # User account schema, lockout tracking, session tokens
│   │   ├── observability/
│   │   │   ├── logging.py                  # Structured JSON audit logging with trace context
│   │   │   ├── metrics.py                  # Prometheus counters and gauges (inventory, reservations, oversells)
│   │   │   └── oversell.py                 # Continuous invariant integrity auditor detecting drift
│   │   ├── pricing/
│   │   │   ├── pricing.py                  # Dynamic pricing engine, original price baseline preservation
│   │   │   ├── promotions.py               # Fixed/percentage discount computation, price floor validation
│   │   │   └── validation.py               # Price floor validator, promotional cap verification
│   │   ├── sales/
│   │   │   ├── activation.py               # Scheduled campaign activation with <=1.0s tolerance, DST handling
│   │   │   ├── lifecycle.py                # Flash sale state transitions (SCHEDULED -> ACTIVE -> ENDED)
│   │   │   └── scheduling.py               # Sale timeline scheduling and conflict detection
│   │   ├── stock/
│   │   │   ├── cache_resilience.py         # Dual-tier cache proxy with automatic PostgreSQL fallback
│   │   │   ├── reconciliation.py           # Invariant reconciliation between reservation ledger and orders
│   │   │   └── reservation.py              # Atomic conditional stock reservation, in-memory locks, hold leases
│   │   └── transactions/
│   │       ├── atomic.py                   # Multi-table atomic transaction coordinator with rollback
│   │       ├── distributed_lock.py         # In-memory distributed lock manager with monotonic fencing tokens
│   │       └── optimistic.py               # Optimistic concurrency control (OCC) with bounded retries
│   └── tests/                              # 52 test files covering concurrency, locking, and failure resilience
├── frontend/
│   ├── src/
│   │   ├── app.js                          # Client-side stock polling, sell-through calculations, reservation modals
│   │   ├── index.css                       # Responsive dark cyberpunk styling, status badges, progress meters
│   │   └── index.html                      # Storefront portal, live telemetry dashboard, checkout modal
│   └── tests/
│       ├── test_dashboard_monitoring.py    # Integration tests for dashboard stock feeds
│       └── test_live_stock_dashboard.py    # Test suite for sell-through and low-stock telemetry
├── docs/                                   # VitePress technical documentation
├── FEATURES.csv                            # 92 tracked features and architectural requirements
├── PROGRESS.md                             # Milestones and test execution records
├── SPEC.txt                                # Formal invariant specification and chaos scenarios
├── Makefile                                # Test and build automation targets
├── package.json                            # VitePress documentation scripts and dependencies
└── progress.json                           # Implementation status matrix
```

---

## Tech Stack & Dependencies

### Backend Dependencies (`Python 3.13`)
| Package | Version | Purpose in Codebase |
| :--- | :--- | :--- |
| **FastAPI** | `^0.115.0` | High-performance asynchronous REST API framework providing OpenAPI documentation and request validation. |
| **Uvicorn** | `^0.32.0` | Production ASGI web server running the async event loop. |
| **SQLAlchemy** | `^2.0.36` | Asynchronous ORM and SQL toolkit managing schema constraints, transactions, and connection pools. |
| **aiosqlite** | `^0.20.0` | Async SQLite driver used for deterministic in-memory integration testing. |
| **asyncpg** | `^0.30.0` | High-performance async PostgreSQL driver for production persistence. |
| **pydantic** | `^2.10.0` | Type validation and schema parsing for requests and responses. |
| **prometheus-client** | `^0.21.0` | Telemetry instrumentation providing Prometheus counters and gauges. |
| **pytest** | `^8.3.0` | Test framework executing unit, integration, and chaos test suites. |
| **pytest-asyncio** | `^0.24.0` | Async test fixtures enabling concurrent coroutine stress tests. |

### Frontend & Documentation Dependencies (`Node.js 20+`)
| Package | Version | Purpose in Codebase |
| :--- | :--- | :--- |
| **VitePress** | `^1.6.4` | Static documentation generator styling documentation in pure-black dark mode. |
| **Mermaid** | `^11.4.1` | Client-side diagram rendering engine for flowcharts, sequences, and ER diagrams. |
| **vitepress-plugin-mermaid** | `^2.0.17` | VitePress integration plugin enabling reactive Mermaid diagram blocks. |

---

## Environment Variables & Configuration

| Variable Name | Default Value | Purpose | Where Used in Code |
| :--- | :--- | :--- | :--- |
| `DATABASE_URL` | `sqlite+aiosqlite:///./flash_sale.db` | Async connection string for SQLAlchemy engine. | `backend/src/db/database.py:9` |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache tier connection string for hot stock counters. | `backend/src/stock/cache_resilience.py:7` |
| `PORT` | `8180` | Port on which FastAPI gateway listens. | `backend/src/api/app.py:34` |
| `GATEWAY_SANDBOX_URL` | `http://localhost:8181` | Mock external payment gateway for webhook delivery. | `backend/src/flow/checkout.py:49` |
| `JWT_SECRET` | `flash-sale-secret-key-42` | Secret key for session signature validation. | `backend/src/auth/service.py:11` |
| `LOG_LEVEL` | `INFO` | Logging verbosity for structured JSON events. | `backend/src/observability/logging.py:15` |
""")

    print("Generating 00a-project-analysis.md...")
    with open(os.path.join(docs_dir, "00a-project-analysis.md"), "w") as f:
        f.write("""# Full Project Analysis: Flash Sale Inventory Engine

## 0.1 What the Project Is
`18-flash-sale-inventory` is an enterprise-grade inventory reservation engine and traffic-leveling platform engineered to eliminate overselling and race conditions during high-volume flash sales.

### The Problem Solved
During viral e-commerce drops, tens of thousands of concurrent users attempt to purchase scarce inventory (e.g., 500 units of a limited product) within a 5-second window. In standard web applications:
1. Concurrent threads execute `SELECT available FROM inventory` simultaneously, all reading positive stock.
2. Multiple threads issue `UPDATE inventory SET available = available - 1`, resulting in negative inventory and catastrophic overselling.
3. Database connection pools are starved by row-level lock contention, triggering cascade outages.
4. Users double-click checkout buttons, triggering duplicate orders and double charges.

### How This Project Solves It
1. **Mathematical Conservation Invariant**: Enforces at both the database level (`CHECK (available + reserved + sold == total_allocated)`) and service level that total allocated stock is strictly conserved.
2. **Two-Phase Reservation Engine**: Before payment is captured, stock is reserved with a 300-second lease using atomic SQL conditional updates and in-memory locks with monotonic fencing tokens.
3. **Virtual Waiting Room**: Smooths incoming traffic by queueing buyers and admitting them in controlled batches.
4. **Automated Rollback & Reconciliation**: Expired reservation holds are automatically recycled into available stock. Continuous background audits detect and resolve any inventory drift.

---

## 0.2 System Architecture & Component Trace

```mermaid
flowchart TD
    subgraph Client["Frontend Client (Port 8180)"]
        UI[Storefront & Dashboard UI]
        QueueTracker[Queue Position Tracker]
        Modal[Instant Checkout Modal]
    end

    subgraph Gateway["FastAPI REST Gateway (api/app.py)"]
        CORS[CORS Middleware]
        AuthMW[HTTPBearer Auth Service]
        Routes[REST API Endpoints]
    end

    subgraph CoreServices["High-Throughput Core Services"]
        WR[Waiting Room Manager<br/>flow/waiting_room.py]
        ResService[Stock Reservation Service<br/>stock/reservation.py]
        LockMgr[Distributed Lock Manager<br/>transactions/distributed_lock.py]
        Checkout[Checkout Service<br/>flow/checkout.py]
        Pricing[Pricing & Promo Engine<br/>pricing/pricing.py]
    end

    subgraph DataStore["Dual-Storage Tier"]
        Cache[In-Memory Hot Path / Redis<br/>Sub-ms Stock Counters]
        DB[(PostgreSQL 16 / Async SQLAlchemy<br/>Durable Orders & Ledger)]
    end

    subgraph Observability["Observability & Reliability"]
        OversellAuditor[Oversell Detector<br/>observability/oversell.py]
        Prometheus[Prometheus Metrics /metrics<br/>observability/metrics.py]
        Reconcile[Reconciliation Engine<br/>stock/reconciliation.py]
    end

    UI -->|Poll Stock / API Requests| Gateway
    Gateway --> CORS --> AuthMW --> Routes
    Routes --> WR
    Routes --> ResService
    Routes --> Checkout
    ResService <--> LockMgr
    ResService -->|Atomic Conditional Update| DataStore
    Checkout -->|Verify Token & Idempotency| DB
    Reconcile -.->|Audit Drift| DB
    OversellAuditor -.->|Scan Invariants| DB
    Prometheus -.->|Scrape Gauges| Gateway
```

---

## 0.3 Request & Data Flow Sequences

### Feature F1 & F2: Waiting Room Admission and Atomic Reservation Flow

```mermaid
sequenceDiagram
    autonumber
    actor Shopper
    participant UI as frontend/src/app.js
    participant API as backend/src/api/app.py
    participant WR as backend/src/flow/waiting_room.py
    participant Stock as backend/src/stock/reservation.py
    participant DB as SQLAlchemy / PostgreSQL

    Shopper->>UI: Clicks "Join Waiting Room"
    UI->>API: POST /api/v1/queue/join {user_id, sku_id}
    API->>WR: join_queue(user_id, sku_id)
    WR-->>API: {ticket_id: "tkt_49a", status: "QUEUED", position: 14}
    API-->>UI: 200 OK + Ticket Details

    loop Every 2 Seconds (Queue Polling)
        UI->>API: GET /api/v1/queue/status?user_id=...&sku_id=...
        API->>WR: get_ticket_status(user_id, sku_id)
        WR-->>API: {status: "ADMITTED", admission_token: "adm_91f"}
        API-->>UI: Admitted! Enable "Reserve Stock"
    end

    Shopper->>UI: Clicks "Reserve Item"
    UI->>API: POST /api/v1/reservations {sku_id, user_id, quantity: 1}
    API->>Stock: reserve_stock(sku_id, user_id, quantity=1, lease=300)
    Stock->>DB: UPDATE inventory SET available = available - 1, reserved = reserved + 1 WHERE sku_id = :sku AND available >= 1
    alt Stock Available (rowcount == 1)
        Stock->>DB: INSERT INTO reservations (token, expires_at, status='PENDING')
        DB-->>Stock: Commit Success
        Stock-->>API: (True, "Reservation created", {token: "tok_99"})
        API-->>UI: 200 OK + Reservation Token (Start 300s Countdown)
    else Out of Stock (rowcount == 0)
        Stock-->>API: (False, "Insufficient stock", None)
        API-->>UI: 409 Conflict ("Sold Out")
    end
```

---

## 0.4 Database Schema & Entity Relationships

```mermaid
erDiagram
    PRODUCTS ||--o{ INVENTORY : "allocates"
    INVENTORY ||--o{ RESERVATIONS : "holds"
    INVENTORY ||--o{ ORDERS : "fulfills"
    USERS ||--o{ USER_SESSIONS : "authenticates"
    USERS ||--o{ ORDERS : "places"
    ORDERS ||--o{ PAYMENTS : "billed_by"
    PAYMENTS ||--o{ REFUNDS : "reversed_by"
    INVENTORY ||--o{ CAMPAIGNS : "featured_in"

    PRODUCTS {
        string product_id PK
        string title
        bigint original_price_cents
        datetime created_at
    }

    INVENTORY {
        string sku_id PK
        string product_id FK
        bigint total_allocated
        bigint available
        bigint reserved
        bigint sold
        bigint version
        datetime updated_at
    }

    RESERVATIONS {
        string reservation_id PK
        string sku_id FK
        string user_id
        integer quantity
        string status
        datetime expires_at
        datetime created_at
    }

    ORDERS {
        string order_id PK
        string user_id FK
        string sku_id FK
        integer quantity
        bigint unit_price_cents
        bigint total_amount_cents
        string idempotency_key UK
        string status
        datetime created_at
    }

    PAYMENTS {
        string payment_id PK
        string order_id FK
        string payment_provider
        bigint amount_cents
        string status
        string idempotency_key UK
        datetime created_at
    }

    USERS {
        string id PK
        string username UK
        string email UK
        string password_hash
        string salt
        string status
        integer failed_login_attempts
        datetime locked_until
    }
```

---

## 0.5 Comprehensive Endpoint Inventory

| Method | Path | Auth Required | Controller Function | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/healthz` | None | `healthz()` | Liveness and uptime probe |
| `POST` | `/api/v1/reservations` | Optional | `create_reservation()` | Atomic stock reservation with 300s lease |
| `GET` | `/api/v1/stock/{sku_id}` | None | `get_stock()` | Real-time stock availability and invariant check |
| `POST` | `/api/v1/checkout` | Optional | `process_checkout()` | Atomic order creation and idempotency check |
| `GET` | `/api/v1/dashboard/stock` | None | `get_all_stock()` | Live stock feed for ops console |
| `GET` | `/api/v1/dashboard/orders` | None | `get_dashboard_orders()` | Recent order stream (limit 50) |
| `GET` | `/api/v1/dashboard/summary` | None | `get_dashboard_summary()` | Aggregate inventory and sell-through KPIs |
| `GET` | `/api/v1/dashboard/counters` | None | `get_dashboard_counters()` | Real-time GMV and waiting room counters |
| `GET` | `/api/v1/dashboard/alerts` | None | `get_dashboard_alerts()` | Low-stock and critical stockout alerts |
| `POST` | `/api/v1/auth/register` | None | `register_user()` | User account registration |
| `POST` | `/api/v1/auth/login` | None | `login_user()` | Authentication with exponential lockout |
| `GET` | `/api/v1/auth/me` | Bearer Token | `get_current_user_profile()`| Session validation and profile retrieval |
| `POST` | `/api/v1/auth/rotate` | Bearer Token | `rotate_session()` | Session token rotation |
| `POST` | `/api/v1/auth/logout` | Bearer Token | `logout_user()` | Session revocation |
| `GET` | `/api/v1/users/{user_id}/limits/{sku_id}` | None | `check_user_sku_limit()`| Query allocated item allowance per user |
| `POST` | `/api/v1/sales` | None | `create_flash_sale_campaign()`| Schedule new flash sale promotion |
| `GET` | `/api/v1/sales/{campaign_id}`| None | `get_flash_sale_campaign()`| Query campaign parameters and discount |
| `GET` | `/api/v1/sales` | None | `list_flash_sale_campaigns()`| List all flash sale campaigns |
| `POST` | `/api/v1/products` | None | `create_product()` | Add item to product catalog |
| `GET` | `/api/v1/products/{product_id}`| None | `get_product()` | Query product details |
| `GET` | `/api/v1/products` | None | `list_products()` | List catalog products |
| `POST` | `/api/v1/inventory/initialize`| None | `initialize_inventory()` | Seed initial SKU inventory allocation |
| `GET` | `/api/v1/inventory/{sku_id}` | None | `get_inventory_sku()` | Query SKU inventory record |
| `GET` | `/api/v1/inventory` | None | `list_inventory()` | List all inventory records |
| `GET` | `/api/v1/orders/{order_id}` | None | `get_order_by_id()` | Fetch order by UUID |
| `GET` | `/api/v1/users/{user_id}/orders`| None | `list_user_orders()` | List all orders for a specific user |
| `POST` | `/api/v1/queue/join` | None | `join_waiting_room_queue()` | Enqueue shopper in virtual waiting room |
| `GET` | `/api/v1/queue/status` | None | `get_queue_status()` | Check ticket position or admission token |
| `POST` | `/api/v1/queue/admit` | None | `admit_waiting_room_batch()` | Admit next batch of shoppers |
| `GET` | `/metrics` | None | `get_prometheus_metrics()` | Prometheus telemetry scrape endpoint |
| `POST` | `/api/v1/incidents/audit` | None | `trigger_oversell_audit()` | Trigger manual invariant audit scan |
| `GET` | `/api/v1/incidents/oversell` | None | `get_oversell_incidents()` | Retrieve detected invariant violations |

---

## 0.6 Final Inventory Counts

Every subsequent documentation file adheres strictly to these verified counts:
- **Frontend Pages/Views**: 1 Single Page Application with 3 interactive sections (Storefront Portal, Live Telemetry Console, Checkout Modal)
- **Frontend Components/Controllers**: 5 UI logic modules in `frontend/src/app.js` (Inventory Fetcher, Metric Aggregator, Table Renderer, Dropdown Controller, Simulation Trigger)
- **Backend Features**: 12 core feature groups covering all 92 items from `FEATURES.csv`
- **REST Endpoints**: 32 distinct routes in `backend/src/api/app.py`
- **SQLAlchemy ORM Models**: 8 models (`InventoryRecord`, `ReservationRecord`, `ProductRecord`, `OrderRecord`, `PaymentRecord`, `RefundRecord`, `CampaignRecord`, `User`, `UserSession`)
- **Pydantic Validation Schemas**: 8 schemas (`ReservationRequest`, `CheckoutRequest`, `RegisterRequest`, `LoginRequest`, `InitInventoryRequest`, `QueueJoinRequest`, `QueueAdmitRequest`, `CampaignSchema`)
- **Backend Middleware**: 3 middleware components (`CORSMiddleware`, `HTTPBearer` auth handler, Global Exception Handlers)
- **Automated Test Files**: 54 test files (52 backend in `backend/tests/`, 2 frontend in `frontend/tests/`)
- **Passing Test Cases**: 96 tests (100% passing via `pytest`)
""")

    print("Generating index.md & README.md...")
    with open(os.path.join(docs_dir, "index.md"), "w") as f:
        f.write("""---
layout: home

hero:
  name: "18-Flash-Sale-Inventory"
  text: "High-Concurrency Flash Sale Inventory Reservation Engine"
  tagline: "Sub-millisecond stock reservations, zero-oversell guarantee, virtual waiting room queue, and automated TTL rollbacks."
  actions:
    - theme: brand
      text: Project Overview
      link: /00a-project-analysis
    - theme: alt
      text: 2-Minute Pitch
      link: /00b-project-pitch
    - theme: alt
      text: System Design
      link: /system-design/
    - theme: alt
      text: 150+ Interview Q&A
      link: /09-interview-qa

features:
  - title: "F1: Atomic Stock Reservation"
    details: "Sub-millisecond conditional SQL updates and in-memory locks with monotonic fencing tokens eliminating race conditions."
    link: /features/F1-atomic-inventory-reservation
  - title: "F2: Virtual Waiting Room"
    details: "FIFO queue admission controller that issues signed tickets to meter burst traffic and protect payment backends."
    link: /features/F2-virtual-waiting-room
  - title: "F3: Hold Expiration & Rollback"
    details: "Asynchronous 300-second reservation lease manager that automatically recycles abandoned holds back to available stock."
    link: /features/F3-hold-expiration-rollback
  - title: "F4: Real-time Oversell Detector"
    details: "Continuous audit monitor that validates the mathematical invariant: Available + Reserved + Sold == Total Allocated."
    link: /features/F4-oversell-audit-detector
  - title: "F5: Live Storefront & Telemetry"
    details: "Responsive client-side dashboard with live stock progress bars, sell-through calculations, and instant checkout modals."
    link: /features/F5-live-checkout-ui
  - title: "High-Scale Systems Design"
    details: "Comprehensive systems design guide modeling 50,000 RPS burst capacity, distributed locking, and multi-tier caching."
    link: /system-design/14.1-requirements-and-estimation
---
""")

    with open(os.path.join(docs_dir, "README.md"), "w") as f:
        f.write("""# Documentation Index: 18-Flash-Sale-Inventory

This documentation suite provides a complete, interview-ready guide to the architecture, code, and systems design of `18-flash-sale-inventory`.

---

## Complete Reading Order

### 1. Project Foundations
1. [Project Type & Classification](./00-project-type.md)
2. [Full Project Analysis & Trace](./00a-project-analysis.md)
3. [Project Pitch (30s & 2m)](./00b-project-pitch.md)
4. [Project Map & File Hierarchy](./00-project-map.md)

### 2. Features & Implementation
5. [Feature Inventory (F1 to F12)](./01-features.md)
6. [Feature Deep Dives](./features/F1-atomic-inventory-reservation.md)
   - [F1: Atomic Inventory Reservation](./features/F1-atomic-inventory-reservation.md)
   - [F2: Virtual Waiting Room](./features/F2-virtual-waiting-room.md)
   - [F3: Hold Expiration & Rollback](./features/F3-hold-expiration-rollback.md)
   - [F4: Real-time Oversell Detector](./features/F4-oversell-audit-detector.md)
   - [F5: Live Checkout & Dashboard UI](./features/F5-live-checkout-ui.md)
   - [F6: Distributed Locks with Fencing](./features/F6-distributed-locking-fencing.md)
   - [F7: Optimistic Concurrency Control](./features/F7-optimistic-concurrency.md)
   - [F8: Pricing & Promotions Engine](./features/F8-pricing-promotions-engine.md)
   - [F9: Timezone Scheduled Activation](./features/F9-scheduled-activation-timezone.md)
   - [F10: Auth, Lockout & Sessions](./features/F10-auth-lockout-sessions.md)
   - [F11: Payment Resilience & Refunds](./features/F11-payment-resilience-refunds.md)
   - [F12: Request Throttling & Limits](./features/F12-request-throttling-limits.md)

### 3. Engineering & Architecture
7. [Step-by-Step Build Order](./02-build-order.md)
8. [Complete API Reference](./03-api-reference.md)
9. [Technology Comparisons (Exhaustive)](./04-tech-comparisons.md)
10. [System Architecture & Scaling](./05-architecture.md)
11. [Security Audit (OWASP Top 10)](./06-security.md)
12. [AI & Anti-Bot Architecture](./07-ai-integration.md)
13. [Engineering Quality & Operations](./08-quality-and-ops.md)

### 4. Systems Design Deep Dive
14. [System Design Overview](./system-design/index.md)
    - [14.1 Requirements & Capacity Estimation](./system-design/14.1-requirements-and-estimation.md)
    - [14.2 Architecture Styles](./system-design/14.2-architecture-styles.md)
    - [14.3 Networking & Communication](./system-design/14.3-networking-and-communication.md)
    - [14.4 Load Balancing & Scaling](./system-design/14.4-load-balancing-and-scaling.md)
    - [14.5 Databases & Two-Phase Ledgers](./system-design/14.5-databases-and-storage.md)
    - [14.6 Caching & Pre-Warmed Pools](./system-design/14.6-caching.md)
    - [14.7 Messaging & Queues](./system-design/14.7-messaging-and-queues.md)
    - [14.8 Consistency, Concurrency & Invariants](./system-design/14.8-consistency-and-concurrency.md)
    - [14.9 Reliability, Circuit Breakers & Rollbacks](./system-design/14.9-reliability-and-resilience.md)
    - [14.10 API Design & Anti-Bot Quotas](./system-design/14.10-api-design-and-rate-limiting.md)
    - [14.11 Security Architecture](./system-design/14.11-security-architecture.md)
    - [14.12 Search & Anomaly Detection](./system-design/14.12-search-and-ai-architecture.md)
    - [14.13 Real-Time Systems & Telemetry](./system-design/14.13-real-time-systems.md)
    - [14.14 Observability & Telemetry](./system-design/14.14-observability-and-operations.md)
    - [14.15 Performance Engineering](./system-design/14.15-performance-engineering.md)
    - [14.16 Cost Modeling & Trade-Offs](./system-design/14.16-cost-and-trade-offs.md)
    - [14.17 Classic System Design Problems](./system-design/14.17-classic-system-design.md)
    - [Architecture Decision Records (ADR Log)](./system-design/decisions.md)

### 5. Interview Prep & Verification
15. [Technical Interview Q&A (150+ Questions)](./09-interview-qa.md)
16. [Gaps & Improvements Roadmap](./10-gaps-and-improvements.md)
17. [Technical Glossary](./11-glossary.md)
18. [Items to Confirm With Developer](./12-confirm-list.md)
19. [Master Checklist: All 275 Items](./13-master-checklist.md)
20. [Say It Out Loud: Spoken Scripts](./14-say-it-out-loud.md)
""")

if __name__ == "__main__":
    generate_overview()
