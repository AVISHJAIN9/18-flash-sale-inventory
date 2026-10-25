# Project Type Detection & Adaptation Track

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
