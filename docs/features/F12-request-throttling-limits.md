# F12: Request Throttling, Burst Smoothing & Quota Enforcement

## Technical Overview
The Throttling Engine (`flow/throttling.py`) protects the gateway from Denial of Service (DoS) and unfair client hoarding using a **Token Bucket Algorithm**:
1. **Smooth Refill**: Refills tokens at a constant rate (e.g. 20 tokens/sec).
2. **Burst Capacity**: Allows short-term bursts up to a configurable maximum (e.g. 50 tokens).
3. **Per-SKU Quotas**: Prevents scalpers from exceeding purchase limits across multiple orders.

### Trace & Implementation
- **Source Files**: `backend/src/flow/throttling.py:23-110`
- **Key Classes**: `TokenBucketThrottler`, `PerSkuPurchaseLimiter`
- **Key Methods**: `acquire(client_id, tokens_requested)`, `assert_within_sku_limit(user_id, sku_id)`


### Request Throttling Architecture Diagram
```mermaid
flowchart LR
    Client[Incoming Checkout Request] --> Ingress[Nginx / API Gateway]
    Ingress --> TokenBucket[Token Bucket Limiter (1,000 req/sec)]
    TokenBucket --> CheckQuota{Tokens Available?}
    CheckQuota -->|Yes| FastAPIServer[FastAPI Reservation Controller]
    CheckQuota -->|No| Drop[HTTP 429 Too Many Requests]
    FastAPIServer --> StockLock[SKU In-Memory Concurrency Lock]
```

### Say It Out Loud
> "I implemented request throttling and burst smoothing in `src/flow/throttling.py` using a Token Bucket rate limiter.
>
> The token bucket refills continuously at 20 tokens per second with a burst capacity of 50 tokens. This allows legitimate shoppers to burst through checkout steps smoothly while throttling malicious automated bots.
>
> If a client exceeds their allowance, the throttler returns `False` along with the exact fractional seconds to wait before retrying, ensuring fair and predictable access for all shoppers."
