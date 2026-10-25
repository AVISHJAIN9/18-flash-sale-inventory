# Technical Glossary

- **Atomic Conditional Update**: A single SQL statement (`UPDATE ... WHERE condition`) that evaluates availability and applies decrements atomically inside the database engine without holding open application-level locks.
- **Conservation Invariant**: The mathematical law $Available + Reserved + Sold == Total Allocated$ that must evaluate to true across all points in time.
- **Fencing Token**: A monotonically increasing integer issued by a distributed lock manager to detect and reject stale writes from paused or partitioned clients.
- **Idempotency Key**: A unique client-supplied token (UUID) ensuring an operation (e.g. payment or order creation) is executed exactly once even when retried multiple times.
- **Optimistic Concurrency Control (OCC)**: A concurrency management method that assumes conflicts are rare, checking a record's version column at commit time and retrying if conflicts occur.
- **Pessimistic Locking**: Locking a database row (`SELECT FOR UPDATE`) to prevent any other transaction from reading or writing until the lock is released.
- **Token Bucket**: A rate-limiting algorithm where tokens refill at a steady rate and burst requests consume tokens up to bucket capacity.
- **Virtual Waiting Room**: A FIFO queue admission gatekeeper that throttles traffic surges during sale openings, admitting users in metered batches.
