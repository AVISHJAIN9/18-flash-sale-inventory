# F2: Virtual Waiting Room & Traffic Leveling

## Technical Overview
The Virtual Waiting Room (`flow/waiting_room.py`) regulates traffic surges during flash-sale openings. When 50,000 users arrive simultaneously, the waiting room enqueues shoppers into a FIFO waiting queue, issues verifiable admission tickets, and meters entry into the checkout flow in controlled batches matching downstream gateway capacity.

```mermaid
flowchart TD
    Shoppers[Surge of 50,000 Users] --> WR[Waiting Room Gatekeeper]
    WR --> FIFO[(In-Memory FIFO Queue)]
    FIFO --> Poller[Client Polling / SSE]
    Admin[Batch Admission Worker] -->|Admit 500 every 5s| FIFO
    FIFO -->|Issue Admission Token| Checkout[Downstream Checkout Services]
```

### Trace & Implementation
- **Source Files**: `backend/src/flow/waiting_room.py:36-150`, `backend/src/api/app.py:558-581`
- **Key Class**: `WaitingRoomManager`
- **Key Methods**: `join_queue(user_id, sku_id)`, `get_ticket_status(user_id, sku_id)`, `admit_batch(sku_id, batch_size, lease_seconds)`
- **API Endpoints**: `POST /api/v1/queue/join`, `GET /api/v1/queue/status`, `POST /api/v1/queue/admit`

### Sequence Diagram
```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as frontend/src/app.js
    participant API as api/app.py
    participant WR as flow/waiting_room.py

    User->>UI: Lands on Flash Sale Page
    UI->>API: POST /api/v1/queue/join {user_id: "usr_10", sku_id: "sku_shoe"}
    API->>WR: join_queue("usr_10", "sku_shoe")
    WR-->>API: {ticket_id: "tkt_81a", status: "QUEUED", position: 142}
    API-->>UI: 200 OK + Position 142

    loop Polling Status
        UI->>API: GET /api/v1/queue/status?user_id=usr_10&sku_id=sku_shoe
        API->>WR: get_ticket_status("usr_10", "sku_shoe")
        WR-->>API: {status: "QUEUED", position: 84}
        API-->>UI: Update Estimated Wait: 8 Seconds
    end

    Note over WR: Batch Admission Worker executes admit_batch(sku_id, 100, 120)
    UI->>API: GET /api/v1/queue/status?user_id=usr_10&sku_id=sku_shoe
    API->>WR: get_ticket_status("usr_10", "sku_shoe")
    WR-->>API: {status: "ADMITTED", admission_token: "adm_9b2", expires_at: 1719200720}
    API-->>UI: 200 OK + Admission Token (Redirect to Checkout)
```

### Say It Out Loud
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
