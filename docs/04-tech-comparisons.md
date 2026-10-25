# Technology Choices & Exhaustive Comparisons

This document provides exhaustive comparisons across 8 major architectural categories, detailing the chosen technology versus all realistic industry alternatives.

---

## 1. Concurrency Control: Atomic SQL Conditional Updates vs Redis Lua vs Pessimistic SELECT FOR UPDATE vs Optimistic Locking (OCC)

| Evaluation Factor | Atomic Conditional SQL [This Project] | Redis Lua Scripts | Postgres SELECT FOR UPDATE | Optimistic Concurrency (OCC) |
| :--- | :--- | :--- | :--- | :--- |
| **Throughput (Contended Single SKU)** | **8,000 - 15,000 RPS** | 50,000+ RPS | 500 - 1,200 RPS | Poor under high contention (<500 RPS) |
| **Oversell Guarantee** | **100% Guaranteed by DB Kernel** | 100% Guaranteed (Single Thread) | 100% Guaranteed (Row Lock) | Guaranteed via version checks |
| **Crash Durability** | **Instant (ACID WAL)** | Asynchronous (AOF/RDB loss risk) | Instant (ACID WAL) | Instant (ACID WAL) |
| **Deadlock Risk** | **Zero (Single atomic statement)** | Zero | High (Multi-row locks) | Zero (Retry loop aborts) |
| **Implementation Complexity** | **Low** | Medium | Low | Medium |

- **Why I Used This**: Atomic conditional updates (`UPDATE ... WHERE available >= :q`) execute in a single SQL round-trip, leveraging Postgres row locks for microsecond durations while avoiding lock wait queues.
- **Why I Did Not Use Alternatives**:
  - *Redis Lua*: While faster in raw memory, Redis requires complex two-phase commit synchronization with Postgres. If Redis crashes before flushing to Postgres, reservation state is lost.
  - *SELECT FOR UPDATE*: Holds row locks across multiple application round-trips, starving connection pools under 50,000 RPS.
  - *Optimistic Concurrency Control (OCC)*: Under 90%+ contention, 95% of OCC threads fail version matching and enter expensive retry loops, consuming excessive CPU.
- **30-Second Spoken Answer**:
  > "I chose atomic conditional SQL updates with database CHECK constraints because they guarantee zero overselling at the database engine level without holding open pessimistic lock queues. Unlike Redis alone, there is zero risk of cache drift or lost reservation state during crash recovery."

---

## 2. Web Framework: FastAPI (Python 3.13) vs Express.js vs Spring Boot vs Go Gin vs NestJS

| Evaluation Factor | FastAPI [This Project] | Express.js (Node) | Spring Boot (Java) | Go Gin |
| :--- | :--- | :--- | :--- | :--- |
| **Async Performance** | **High (uvloop ASGI)** | High (Node Event Loop) | Very High (Virtual Threads) | Ultra High (Goroutines) |
| **Type Safety & Schemas** | **Pydantic v2 (Rust-backed)** | Manual / Joi / Zod | Static Strong Typing | Static Strong Typing |
| **Auto OpenAPI Docs** | **Built-in Interactive Swagger** | Manual Swagger configuration | Springfox / Springdoc | Manual Swagger |
| **Developer Velocity** | **Very High** | High | Medium | Medium |

- **Why I Used This**: FastAPI provides native Python async/await, automated Pydantic schema validation compiled in Rust, and instant Swagger API documentation.
- **Why I Did Not Use Alternatives**:
  - *Express.js*: Lacks native schema validation and automatic OpenAPI generation; requires callback/promise chaining wrappers for clean error propagation.
  - *Go Gin*: High performance, but slower developer iteration time for complex state machine logic.

---

## 3. Database Layer: PostgreSQL 16 + Async SQLAlchemy vs MongoDB vs DynamoDB vs MySQL

| Evaluation Factor | PostgreSQL 16 [This Project] | MongoDB | AWS DynamoDB | MySQL 8.0 |
| :--- | :--- | :--- | :--- | :--- |
| **Data Integrity / CHECKs**| **Strict Table CHECK Constraints** | Document validation rules | Condition expressions | Basic CHECK constraints |
| **Isolation Guarantees** | **Full ACID (Read Committed to Serializable)** | Multi-document ACID (High latency) | Eventual consistency default | Full ACID (InnoDB) |
| **Connection Pooling** | **Asyncpg connection pooling** | Mongoose driver pool | HTTP Request-based | aiomysql pool |

- **Why I Used This**: Flash sales require absolute mathematical conservation invariants. PostgreSQL's check constraints (`CHECK (available + reserved + sold == total_allocated)`) guarantee that corrupted states are rejected by the database engine.
