---
layout: home

hero:
  name: "18-Flash-Sale-Inventory"
  text: "High-Concurrency Flash Sale Inventory Reservation Engine"
  tagline: "Sub-millisecond stock reservations, zero-oversell guarantee, virtual waiting room queue, and automated TTL rollbacks."
  actions:
    - theme: brand
      text: Project Overview
      link: /00a-project-analysis
    - theme: alt
      text: 2-Minute Pitch
      link: /00b-project-pitch
    - theme: alt
      text: System Design
      link: /system-design/
    - theme: alt
      text: 150+ Interview Q&A
      link: /09-interview-qa

features:
  - title: "F1: Atomic Stock Reservation"
    details: "Sub-millisecond conditional SQL updates and in-memory locks with monotonic fencing tokens eliminating race conditions."
    link: /features/F1-atomic-inventory-reservation
  - title: "F2: Virtual Waiting Room"
    details: "FIFO queue admission controller that issues signed tickets to meter burst traffic and protect payment backends."
    link: /features/F2-virtual-waiting-room
  - title: "F3: Hold Expiration & Rollback"
    details: "Asynchronous 300-second reservation lease manager that automatically recycles abandoned holds back to available stock."
    link: /features/F3-hold-expiration-rollback
  - title: "F4: Real-time Oversell Detector"
    details: "Continuous audit monitor that validates the mathematical invariant: Available + Reserved + Sold == Total Allocated."
    link: /features/F4-oversell-audit-detector
  - title: "F5: Live Storefront & Telemetry"
    details: "Responsive client-side dashboard with live stock progress bars, sell-through calculations, and instant checkout modals."
    link: /features/F5-live-checkout-ui
  - title: "High-Scale Systems Design"
    details: "Comprehensive systems design guide modeling 50,000 RPS burst capacity, distributed locking, and multi-tier caching."
    link: /system-design/14.1-requirements-and-estimation
---
