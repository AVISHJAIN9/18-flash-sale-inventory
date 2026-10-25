# System Architecture & Scaling

## High-Level Architecture Flowchart

```mermaid
flowchart TD
    subgraph Traffic["Incoming High-Concurrency Traffic"]
        Burst[50,000 Burst Shoppers]
    end

    subgraph Edge["Edge & Traffic Leveling"]
        CDN[Edge CDN - Static Assets]
        LB[Layer 7 Load Balancer]
        WR[Virtual Waiting Room - flow/waiting_room.py]
    end

    subgraph Gateway["Application Cluster (Stateless FastAPI Replicas)"]
        API1[FastAPI Node 1]
        API2[FastAPI Node 2]
        API3[FastAPI Node N]
    end

    subgraph HotTier["In-Memory Hot Path"]
        Redis[(Redis 7 Cluster<br/>Atomic Lua Counters & Queue)]
        LockMgr[Distributed Lock Manager<br/>transactions/distributed_lock.py]
    end

    subgraph DurableTier["Durable Persistence Layer"]
        PrimaryDB[(PostgreSQL 16 Primary<br/>Durable Orders & Ledger)]
        ReplicaDB[(PostgreSQL Read Replicas<br/>Dashboard & Reporting)]
    end

    subgraph Workers["Background Daemons"]
        ReconcileWorker[Reconciliation Worker<br/>stock/reconciliation.py]
        OversellAuditor[Oversell Incident Detector<br/>observability/oversell.py]
        TTLWorker[Hold Expiration Worker]
    end

    Burst --> CDN
    Burst --> LB
    LB --> WR
    WR -->|Metered Batches| API1 & API2 & API3
    API1 & API2 & API3 <--> HotTier
    API1 & API2 & API3 -->|Commit Orders| PrimaryDB
    PrimaryDB -.->|Streaming Replication| ReplicaDB
    ReconcileWorker -.->|Audit Invariants| PrimaryDB
    TTLWorker -.->|Release Expired Holds| PrimaryDB
    OversellAuditor -.->|Continuous Audit| PrimaryDB
```

---

## 100x Scale-Up & The First 3 Bottlenecks
When traffic scales from 1,000 RPS to 100,000 RPS:
1. **Bottleneck 1: Database Row Contention on Hot SKU**: 100,000 requests attempting to update the same single database row will hit row-level write lock queues.
   - *Fix*: Offload inventory counters to **Redis Lua**, maintaining in-memory stock counters and flushing to PostgreSQL in asynchronous batched commits.
2. **Bottleneck 2: Virtual Waiting Room Memory Footprint**: Storing 1,000,000 queued user tickets in FastAPI process memory causes high RAM usage and prevents horizontal scaling.
   - *Fix*: Move queue state to **Redis Sorted Sets (`ZADD`, `ZRANGEBYSCORE`)** with user timestamps as scores.
3. **Bottleneck 3: Third-Party Payment Gateway Rate Limits**: Payment gateways (e.g. Stripe) cap API throughput at 100-500 requests per second.
   - *Fix*: Decouple payment submission via an asynchronous message queue (Apache Kafka or AWS SQS) and process payments via consumer worker pools.
