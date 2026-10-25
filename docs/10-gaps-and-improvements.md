# Gaps & Roadmap Improvements

This document lists architectural improvements ranked by priority for future production iterations.

---

## Priority 0: Critical for Multi-Node Production
1. **Distributed Redis Queue for Waiting Room**: Currently `WaitingRoomManager` holds queue tickets in local process RAM. In a multi-node deployment, moving queue state to Redis Sorted Sets (`ZADD` / `ZRANGE`) will allow horizontal scaling across 20+ FastAPI nodes.
2. **Asynchronous Payment Message Broker**: Direct synchronous calls to external payment gateways create latency bottlenecks. Integrating Apache Kafka or AWS SQS will decouple order placement from payment capture.

---

## Priority 1: High Operational Value
3. **Server-Sent Events (SSE) / WebSocket Push**: Replace the 3-second client polling in `frontend/src/app.js` with SSE streams, reducing unnecessary HTTP request overhead on the `/dashboard/stock` endpoint.
4. **Automated Deadlock Detection & Backoff**: Add automated circuit breakers around Postgres query retries if lock wait timeouts exceed 500ms.

---

## Priority 2: Security & Polish
5. **Hardware Security Fingerprinting**: Enhance anti-scalper scoring with client-side WebAssembly hardware fingerprinting.
6. **Multi-Region Active-Passive Database Replication**: Set up automated cross-region read replicas with automated failover.
