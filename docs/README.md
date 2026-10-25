# Documentation Index: 18-Flash-Sale-Inventory

This documentation suite provides a complete, interview-ready guide to the architecture, code, and systems design of `18-flash-sale-inventory`.

---

## Complete Reading Order

### 1. Project Foundations
1. [Project Type & Classification](./00-project-type.md)
2. [Full Project Analysis & Trace](./00a-project-analysis.md)
3. [Project Pitch (30s & 2m)](./00b-project-pitch.md)
4. [Project Map & File Hierarchy](./00-project-map.md)

### 2. Features & Implementation
5. [Feature Inventory (F1 to F12)](./01-features.md)
6. [Feature Deep Dives](./features/F1-atomic-inventory-reservation.md)
   - [F1: Atomic Inventory Reservation](./features/F1-atomic-inventory-reservation.md)
   - [F2: Virtual Waiting Room](./features/F2-virtual-waiting-room.md)
   - [F3: Hold Expiration & Rollback](./features/F3-hold-expiration-rollback.md)
   - [F4: Real-time Oversell Detector](./features/F4-oversell-audit-detector.md)
   - [F5: Live Checkout & Dashboard UI](./features/F5-live-checkout-ui.md)
   - [F6: Distributed Locks with Fencing](./features/F6-distributed-locking-fencing.md)
   - [F7: Optimistic Concurrency Control](./features/F7-optimistic-concurrency.md)
   - [F8: Pricing & Promotions Engine](./features/F8-pricing-promotions-engine.md)
   - [F9: Timezone Scheduled Activation](./features/F9-scheduled-activation-timezone.md)
   - [F10: Auth, Lockout & Sessions](./features/F10-auth-lockout-sessions.md)
   - [F11: Payment Resilience & Refunds](./features/F11-payment-resilience-refunds.md)
   - [F12: Request Throttling & Limits](./features/F12-request-throttling-limits.md)

### 3. Engineering & Architecture
7. [Step-by-Step Build Order](./02-build-order.md)
8. [Complete API Reference](./03-api-reference.md)
9. [Technology Comparisons (Exhaustive)](./04-tech-comparisons.md)
10. [System Architecture & Scaling](./05-architecture.md)
11. [Security Audit (OWASP Top 10)](./06-security.md)
12. [AI & Anti-Bot Architecture](./07-ai-integration.md)
13. [Engineering Quality & Operations](./08-quality-and-ops.md)

### 4. Systems Design Deep Dive
14. [System Design Overview](./system-design/index.md)
    - [14.1 Requirements & Capacity Estimation](./system-design/14.1-requirements-and-estimation.md)
    - [14.2 Architecture Styles](./system-design/14.2-architecture-styles.md)
    - [14.3 Networking & Communication](./system-design/14.3-networking-and-communication.md)
    - [14.4 Load Balancing & Scaling](./system-design/14.4-load-balancing-and-scaling.md)
    - [14.5 Databases & Two-Phase Ledgers](./system-design/14.5-databases-and-storage.md)
    - [14.6 Caching & Pre-Warmed Pools](./system-design/14.6-caching.md)
    - [14.7 Messaging & Queues](./system-design/14.7-messaging-and-queues.md)
    - [14.8 Consistency, Concurrency & Invariants](./system-design/14.8-consistency-and-concurrency.md)
    - [14.9 Reliability, Circuit Breakers & Rollbacks](./system-design/14.9-reliability-and-resilience.md)
    - [14.10 API Design & Anti-Bot Quotas](./system-design/14.10-api-design-and-rate-limiting.md)
    - [14.11 Security Architecture](./system-design/14.11-security-architecture.md)
    - [14.12 Search & Anomaly Detection](./system-design/14.12-search-and-ai-architecture.md)
    - [14.13 Real-Time Systems & Telemetry](./system-design/14.13-real-time-systems.md)
    - [14.14 Observability & Telemetry](./system-design/14.14-observability-and-operations.md)
    - [14.15 Performance Engineering](./system-design/14.15-performance-engineering.md)
    - [14.16 Cost Modeling & Trade-Offs](./system-design/14.16-cost-and-trade-offs.md)
    - [14.17 Classic System Design Problems](./system-design/14.17-classic-system-design.md)
    - [Architecture Decision Records (ADR Log)](./system-design/decisions.md)

### 5. Interview Prep & Verification
15. [Technical Interview Q&A (150+ Questions)](./09-interview-qa.md)
16. [Gaps & Improvements Roadmap](./10-gaps-and-improvements.md)
17. [Technical Glossary](./11-glossary.md)
18. [Items to Confirm With Developer](./12-confirm-list.md)
19. [Master Checklist: All 275 Items](./13-master-checklist.md)
20. [Say It Out Loud: Spoken Scripts](./14-say-it-out-loud.md)
