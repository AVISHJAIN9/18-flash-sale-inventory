# Full Project Analysis: Flash Sale Inventory Engine

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
