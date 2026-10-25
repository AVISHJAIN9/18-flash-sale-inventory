# Complete API Reference

This document provides exhaustive documentation for all 32 REST endpoints exposed by the Flash Sale Gateway (`backend/src/api/app.py`).

---

## Endpoint Summary Table

| Category | Method | Path | Auth | Description |
| :--- | :--- | :--- | :--- | :--- |
| **System** | `GET` | `/healthz` | None | Service liveness and uptime probe |
| **Reservations** | `POST` | `/api/v1/reservations` | Optional | Atomic stock hold creation |
| **Stock** | `GET` | `/api/v1/stock/{sku_id}` | None | Real-time stock status and invariant check |
| **Checkout** | `POST` | `/api/v1/checkout` | Optional | Finalize purchase with idempotency key |
| **Dashboard** | `GET` | `/api/v1/dashboard/stock` | None | Full inventory status feed for ops console |
| **Dashboard** | `GET` | `/api/v1/dashboard/orders` | None | Recent orders feed (limit 50) |
| **Dashboard** | `GET` | `/api/v1/dashboard/summary` | None | Aggregate sell-through KPIs |
| **Dashboard** | `GET` | `/api/v1/dashboard/counters`| None | Real-time GMV and waiting room counters |
| **Dashboard** | `GET` | `/api/v1/dashboard/alerts` | None | Low-stock and critical stockout alerts |
| **Auth** | `POST` | `/api/v1/auth/register` | None | User account registration |
| **Auth** | `POST` | `/api/v1/auth/login` | None | Authentication with exponential lockout |
| **Auth** | `GET` | `/api/v1/auth/me` | Bearer | Session validation and profile info |
| **Auth** | `POST` | `/api/v1/auth/rotate` | Bearer | Session token rotation |
| **Auth** | `POST` | `/api/v1/auth/logout` | Bearer | Session revocation |
| **Limits** | `GET` | `/api/v1/users/{user_id}/limits/{sku_id}` | None | Check remaining item allowance |
| **Sales** | `POST` | `/api/v1/sales` | None | Create new flash sale campaign |
| **Sales** | `GET` | `/api/v1/sales/{campaign_id}`| None | Get flash sale details |
| **Sales** | `GET` | `/api/v1/sales` | None | List all flash sale campaigns |
| **Catalog** | `POST` | `/api/v1/products` | None | Create product |
| **Catalog** | `GET` | `/api/v1/products/{product_id}`| None | Get product details |
| **Catalog** | `GET` | `/api/v1/products` | None | List catalog products |
| **Inventory** | `POST` | `/api/v1/inventory/initialize`| None | Seed SKU allocation |
| **Inventory** | `GET` | `/api/v1/inventory/{sku_id}` | None | Get SKU inventory |
| **Inventory** | `GET` | `/api/v1/inventory` | None | List all SKU inventory |
| **Orders** | `GET` | `/api/v1/orders/{order_id}` | None | Get order details |
| **Orders** | `GET` | `/api/v1/users/{user_id}/orders` | None | List orders for user |
| **Queue** | `POST` | `/api/v1/queue/join` | None | Join waiting room queue |
| **Queue** | `GET` | `/api/v1/queue/status` | None | Poll ticket queue status |
| **Queue** | `POST` | `/api/v1/queue/admit` | None | Admit batch of shoppers |
| **Metrics** | `GET` | `/metrics` | None | Prometheus telemetry text scrape |
| **Audits** | `POST` | `/api/v1/incidents/audit` | None | Trigger manual invariant audit scan |
| **Audits** | `GET` | `/api/v1/incidents/oversell` | None | Retrieve logged oversell incidents |

---

## Detailed Endpoint Specifications

### 1. Atomic Stock Reservation
- **Endpoint**: `POST /api/v1/reservations`
- **Purpose**: Atomically reserves units of a specified SKU, issuing a 300-second lease hold token.
- **Request Body**:
```json
{
  "sku_id": "sku-shoe-cyber-01",
  "user_id": "usr_94a2",
  "quantity": 1,
  "lease_seconds": 300
}
```
- **Validation**: `quantity > 0`, `lease_seconds > 0`, non-empty strings.
- **Success Response (`200 OK`)**:
```json
{
  "success": true,
  "message": "Reservation created atomically",
  "reservation": {
    "reservation_id": "tok_b42f1a90c4",
    "sku_id": "sku-shoe-cyber-01",
    "user_id": "usr_94a2",
    "quantity": 1,
    "status": "PENDING",
    "expires_at": "2026-10-25T16:35:00Z"
  }
}
```
- **Error Responses**:
  - `409 Conflict`: `{"detail": "Insufficient stock or SKU not found"}`
  - `400 Bad Request`: `{"detail": "Quantity must be positive"}`

---

### 2. Process Atomic Checkout
- **Endpoint**: `POST /api/v1/checkout`
- **Purpose**: Executes atomic order finalization, payment capture, and idempotency key recording.
- **Request Body**:
```json
{
  "user_id": "usr_94a2",
  "sku_id": "sku-shoe-cyber-01",
  "quantity": 1,
  "unit_price_cents": 12000,
  "reservation_token": "tok_b42f1a90c4",
  "idempotency_key": "idem_order_88291a",
  "max_quantity_per_user": 2
}
```
- **Success Response (`200 OK`)**:
```json
{
  "success": true,
  "message": "Order created successfully",
  "order": {
    "order_id": "ord_77192",
    "user_id": "usr_94a2",
    "sku_id": "sku-shoe-cyber-01",
    "quantity": 1,
    "total_amount_cents": 12000,
    "status": "PAID",
    "is_replay": false
  }
}
```
- **Idempotent Replay (`200 OK`)**: Returns existing order with `"is_replay": true`.
- **Error Responses**:
  - `400 Bad Request`: Reservation token expired, user limit exceeded, or SKU mismatch.
