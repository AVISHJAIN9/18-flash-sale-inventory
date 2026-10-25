# Project Structure & Dependency Map

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
