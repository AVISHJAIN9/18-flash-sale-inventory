# Engineering Quality, Testing & Operations

## Automated Test Suite Overview
The test suite consists of **54 test files** (52 backend, 2 frontend) delivering **96 passing automated tests** across unit, integration, and chaos scenarios.

```
backend/tests/
├── test_atomic_stock_reservation.py       # Zero oversell under concurrency
├── test_atomic_checkout.py               # Two-phase order creation
├── test_virtual_waiting_room.py          # FIFO queue admission & tickets
├── test_queue_fairness.py                # Uniform queue draw distributions
├── test_payment_idempotency.py           # Duplicate payment request deduplication
├── test_reliability_load.py              # 100-thread concurrent reservation stress test
├── test_reliability_chaos.py             # Database recovery and cache drop resilience
└── test_timezone_activation.py           # DST boundary crossing and 1.0s tolerance
```

### Concurrency Stress Test Analysis
In `backend/tests/test_reliability_load.py`, the system tests extreme contention:
- **Scenario**: 100 concurrent asynchronous tasks attempt to reserve stock for a SKU with only **10 available items**.
- **Assertion**: Exactly **10 tasks** succeed with `200 OK`, and **90 tasks** fail with `409 Conflict`.
- **Invariant Audit**: Immediately following the run, the test asserts that `available == 0`, `reserved == 10`, and `available + reserved + sold == total_allocated`. Zero overselling is confirmed.

---

## Observability & Prometheus Telemetry
The service exposes a standard Prometheus scrape endpoint at `GET /metrics` (`backend/src/observability/metrics.py`):
- `inventory_available_gauge{sku_id="..."}`: Real-time available units.
- `inventory_reserved_gauge{sku_id="..."}`: Active reservation holds.
- `inventory_sold_gauge{sku_id="..."}`: Confirmed purchases.
- `oversell_incidents_total{sku_id="...", severity="..."}`: Critical anomaly counter.
