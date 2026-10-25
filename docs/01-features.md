# Feature Inventory & Architectural Traces

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
