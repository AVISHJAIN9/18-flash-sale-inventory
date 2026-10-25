# Architecture Decision Records (ADR Log)

This log records every major design decision made in `18-flash-sale-inventory`.

| ADR ID | Decision Made | Chosen Option | Alternatives Considered | Deciding Factors | Trade-Off Accepted | Revisit When |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **ADR-01** | High-Concurrency Stock Reservation | **Atomic Conditional SQL (`WHERE available >= :q`)** | Redis Lua, `SELECT FOR UPDATE`, Optimistic Locking | Direct ACID durability, database kernel-enforced check constraints. | Lower single-row throughput ceiling than pure in-memory Redis. | Single SKU traffic exceeds 20,000 writes/sec. |
| **ADR-02** | Traffic Surge Leveling | **Virtual Waiting Room (`flow/waiting_room.py`)** | Direct HTTP 429 Rate Limiting, Unbounded Queue | Preserves customer fairness and prevents payment gateway connection collapse. | Adds asynchronous polling round-trips for the client. | Traffic is distributed over hours rather than sudden drops. |
| **ADR-03** | Currency Precision | **Integer Minor Units (Cents)** | Floating-point numbers, Decimal objects | Eliminates IEEE 754 precision rounding errors and optimizes memory. | Requires frontend multiplication/division by 100 for display. | Multi-currency conversions with 4 decimal places are required. |
| **ADR-04** | Distributed Lock Stale Write Defense | **Monotonic Fencing Tokens (`transactions/distributed_lock.py`)** | Simple Redis lock, Redlock | Eliminates Martin Kleppmann stale-write hazards caused by GC pauses. | Storage layer must record highest observed fencing token. | All writes are handled by a single leader database. |
| **ADR-05** | API Framework | **FastAPI (Python 3.13)** | Express.js, Django, Go Gin | High-performance async ASGI loop, native Pydantic v2 validation, auto-generated OpenAPI docs. | Python global interpreter lock (mitigated by multi-process Uvicorn). | Microsecond-level network proxying is needed (migrate to Go/Rust). |
| **ADR-06** | Observability Architecture | **Prometheus Gauges + Invariant Auditor** | Passive log scanning, ELK stack alone | Continuous autonomous audit detects mathematical drift before customers notice. | Small background query overhead on database. | Database CPU exceeds 80% during peak flash sales. |
