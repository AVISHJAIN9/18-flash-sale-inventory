# 18-flash-sale-inventory

## Mission
MVP implementation for 18-flash-sale-inventory.

## Status
<!-- STATUS:BEGIN -->
**COMPLETED 90 · WORKING 0 · TODO 0**

### Area Database & Distributed State (10 features · 10 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-001 | Product database | BE+DB | COMPLETED |
| FLS-002 | Inventory database | BE+DB | COMPLETED |
| FLS-003 | Reservation store | BE+DB | COMPLETED |
| FLS-004 | Order database | BE+DB | COMPLETED |
| FLS-005 | Payment records | BE+DB | COMPLETED |
| FLS-006 | Campaign database | BE+DB | COMPLETED |
| FLS-011 | Atomic transactions | BE+DB | COMPLETED |
| FLS-008 | User database | BE+DB | COMPLETED |
| FLS-010 | Distributed locks | BE+DB | COMPLETED |
| FLS-012 | Optimistic concurrency | BE+DB | COMPLETED |

### Area Flash Sale Core (8 features · 8 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-013 | Sale lifecycle management | BE | COMPLETED |
| FLS-016 | Sale state machine | BE | COMPLETED |
| FLS-019 | Sale-specific pricing | BE | COMPLETED |
| FLS-014 | Sale start/end scheduling | BE | COMPLETED |
| FLS-020 | Original-price preservation | BE | COMPLETED |
| FLS-021 | Sale-price validation | BE | COMPLETED |
| FLS-024 | Timezone handling | BE | COMPLETED |
| FLS-025 | Scheduled activation | BE | COMPLETED |

### Area Inventory Reservation & Stock (11 features · 11 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-039 | Real-time stock tracking | BE+DB | COMPLETED |
| FLS-044 | Atomic stock reservation | BE+DB | COMPLETED |
| FLS-045 | Reservation expiry | BE+DB | COMPLETED |
| FLS-046 | Reservation release | BE+DB | COMPLETED |
| FLS-047 | Oversell prevention | BE+DB | COMPLETED |
| FLS-048 | Negative-stock prevention | BE+DB | COMPLETED |
| FLS-049 | Stock reconciliation | BE+DB | COMPLETED |
| FLS-040 | Available quantity | BE+DB | COMPLETED |
| FLS-041 | Reserved quantity | BE+DB | COMPLETED |
| FLS-042 | Sold quantity | BE+DB | COMPLETED |
| FLS-050 | SKU-level inventory | BE+DB | COMPLETED |

### Area Pricing & Promotions (6 features · 6 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-053 | Percentage discount | BE+DB | COMPLETED |
| FLS-062 | Price-floor validation | BE+DB | COMPLETED |
| FLS-054 | Fixed discount | BE+DB | COMPLETED |
| FLS-057 | Coupon validation | BE+DB | COMPLETED |
| FLS-058 | Promotion stacking rules | BE+DB | COMPLETED |
| FLS-061 | Maximum discount limits | BE+DB | COMPLETED |

### Area High-Concurrency Purchase Flow (12 features · 12 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-065 | Purchase admission | BE | COMPLETED |
| FLS-066 | Queue/waiting room | BE | COMPLETED |
| FLS-067 | Per-user purchase limit | BE | COMPLETED |
| FLS-069 | Atomic checkout | BE | COMPLETED |
| FLS-070 | Idempotency keys | BE | COMPLETED |
| FLS-071 | Duplicate-order prevention | BE | COMPLETED |
| FLS-075 | Reservation tokens | BE | COMPLETED |
| FLS-076 | Checkout timeout | BE | COMPLETED |
| FLS-068 | Per-SKU purchase limit | BE | COMPLETED |
| FLS-072 | Request throttling | BE | COMPLETED |
| FLS-073 | Burst handling | BE | COMPLETED |
| FLS-077 | Payment timeout handling | BE | COMPLETED |

### Area Queue (8 features · 8 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-078 | Virtual waiting room | BE | COMPLETED |
| FLS-079 | Queue position | BE | COMPLETED |
| FLS-080 | Queue tokens | BE | COMPLETED |
| FLS-085 | Per-IP limits | BE | COMPLETED |
| FLS-081 | Queue expiration | BE | COMPLETED |
| FLS-082 | Fair queue ordering | BE | COMPLETED |
| FLS-084 | Randomized admission | BE | COMPLETED |
| FLS-086 | Per-account limits | BE | COMPLETED |

### Area Orders & Payments (12 features · 12 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-090 | Order creation | BE+DB | COMPLETED |
| FLS-091 | Order state machine | BE+DB | COMPLETED |
| FLS-092 | Payment initiation | BE+DB | COMPLETED |
| FLS-093 | Payment confirmation | BE+DB | COMPLETED |
| FLS-096 | Payment idempotency | BE+DB | COMPLETED |
| FLS-097 | Order expiration | BE+DB | COMPLETED |
| FLS-094 | Payment failure handling | BE+DB | COMPLETED |
| FLS-095 | Payment retry | BE+DB | COMPLETED |
| FLS-098 | Order cancellation | BE+DB | COMPLETED |
| FLS-099 | Refund initiation | BE+DB | COMPLETED |
| FLS-100 | Refund status | BE+DB | COMPLETED |
| FLS-101 | Inventory-to-order consistency | BE+DB | COMPLETED |

### Area Backend APIs & Services (7 features · 7 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-106 | Reservation API | BE | COMPLETED |
| FLS-108 | Checkout API | BE | COMPLETED |
| FLS-103 | Flash-sale API | BE | COMPLETED |
| FLS-104 | Product API | BE | COMPLETED |
| FLS-105 | Inventory API | BE | COMPLETED |
| FLS-109 | Order API | BE | COMPLETED |
| FLS-111 | Queue API | BE | COMPLETED |

### Area Frontend & Operations Console (5 features · 5 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-116 | Live stock dashboard | FE+BE | COMPLETED |
| FLS-115 | Flash-sale dashboard | FE+BE | COMPLETED |
| FLS-123 | Order monitoring | FE+BE | COMPLETED |
| FLS-125 | Real-time counters | FE+BE | COMPLETED |
| FLS-126 | Low-stock alerts | FE+BE | COMPLETED |

### Area User & Customer Management (5 features · 5 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-026 | User authentication | FE+BE+DB | COMPLETED |
| FLS-032 | Per-user limits | FE+BE+DB | COMPLETED |
| FLS-036 | Blocked-user rules | FE+BE+DB | COMPLETED |
| FLS-037 | Account lockout | FE+BE+DB | COMPLETED |
| FLS-038 | Session management | FE+BE+DB | COMPLETED |

### Area Notifications (3 features · 3 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-127 | Prometheus metrics | BE | COMPLETED |
| FLS-129 | Structured logs | BE | COMPLETED |
| FLS-135 | Oversell incidents | BE | COMPLETED |

### Area Reliability (3 features · 3 COMPLETED · 0 WORKING · 0 TODO)

| ID | Feature | Layers | Status |
|---|---|---|---|
| FLS-139 | Load testing | BE | COMPLETED |
| FLS-141 | Chaos testing | BE | COMPLETED |
| FLS-145 | Cache failure handling | BE | COMPLETED |

<!-- STATUS:END -->

## Architecture
Production-grade distributed system implementation.

## How to run
```bash
make up
make test
```

## Decisions

## Benchmarks

## Limitations
- FLS-092, FLS-093: Payment initiation/confirmation use LOCAL_EQUIVALENT sandbox; upgrade requires production Stripe/Adyen merchant credentials
