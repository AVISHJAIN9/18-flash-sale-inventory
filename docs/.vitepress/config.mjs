import { defineConfig } from 'vitepress';
import { withMermaid } from 'vitepress-plugin-mermaid';

export default withMermaid(
  defineConfig({
    title: '18-Flash-Sale-Inventory',
    description: 'High-concurrency atomic flash-sale inventory reservation engine in FastAPI and Redis.',
    appearance: 'dark',
    base: '/',
    themeConfig: {
      nav: [
        { text: 'Guide', link: '/00a-project-analysis' },
        { text: 'Features', link: '/01-features' },
        { text: 'API Reference', link: '/03-api-reference' },
        { text: 'System Design', link: '/system-design/' },
        { text: 'Interview Q&A', link: '/09-interview-qa' },
        { text: 'Master Checklist', link: '/13-master-checklist' }
      ],
      sidebar: [
        {
          text: 'Project Overview',
          items: [
            { text: 'Project Type & Adaptation', link: '/00-project-type' },
            { text: 'Full Project Analysis', link: '/00a-project-analysis' },
            { text: 'Project Pitch (30s & 2m)', link: '/00b-project-pitch' },
            { text: 'Project Map & Hierarchy', link: '/00-project-map' }
          ]
        },
        {
          text: 'Features & Architecture',
          items: [
            { text: 'Feature Inventory (Overview)', link: '/01-features' },
            { text: 'F1: Atomic Inventory Reservation', link: '/features/F1-atomic-inventory-reservation' },
            { text: 'F2: Virtual Waiting Room Queue', link: '/features/F2-virtual-waiting-room' },
            { text: 'F3: Hold Expiration & Rollback', link: '/features/F3-hold-expiration-rollback' },
            { text: 'F4: Real-time Oversell Detector', link: '/features/F4-oversell-audit-detector' },
            { text: 'F5: Live Storefront & UI', link: '/features/F5-live-checkout-ui' },
            { text: 'F6: Distributed Locks & Fencing', link: '/features/F6-distributed-locking-fencing' },
            { text: 'F7: Optimistic Concurrency (OCC)', link: '/features/F7-optimistic-concurrency' },
            { text: 'F8: Pricing & Promotions Engine', link: '/features/F8-pricing-promotions-engine' },
            { text: 'F9: Timezone Scheduled Activation', link: '/features/F9-scheduled-activation-timezone' },
            { text: 'F10: Auth, Lockout & Sessions', link: '/features/F10-auth-lockout-sessions' },
            { text: 'F11: Order Lifecycle & Refunds', link: '/features/F11-payment-resilience-refunds' },
            { text: 'F12: Request Throttling & Limits', link: '/features/F12-request-throttling-limits' },
            { text: 'Build Order from Scratch', link: '/02-build-order' },
            { text: 'Complete API Reference', link: '/03-api-reference' },
            { text: 'Tech Choices & Comparisons', link: '/04-tech-comparisons' }
          ]
        },
        {
          text: 'Security & Operations',
          items: [
            { text: 'System Architecture', link: '/05-architecture' },
            { text: 'Security Audit (OWASP Top 10)', link: '/06-security' },
            { text: 'AI & Anti-Bot Architecture', link: '/07-ai-integration' },
            { text: 'Quality, Tests & Operations', link: '/08-quality-and-ops' }
          ]
        },
        {
          text: 'System Design Deep Dive',
          items: [
            { text: 'System Design Overview', link: '/system-design/' },
            { text: '14.1 Capacity Estimation', link: '/system-design/14.1-requirements-and-estimation' },
            { text: '14.2 Architecture Styles', link: '/system-design/14.2-architecture-styles' },
            { text: '14.3 Networking & Protocols', link: '/system-design/14.3-networking-and-communication' },
            { text: '14.4 Load Balancing & Scaling', link: '/system-design/14.4-load-balancing-and-scaling' },
            { text: '14.5 Databases & Storage', link: '/system-design/14.5-databases-and-storage' },
            { text: '14.6 Caching & Pre-Warmed Pools', link: '/system-design/14.6-caching' },
            { text: '14.7 Messaging & Queues', link: '/system-design/14.7-messaging-and-queues' },
            { text: '14.8 Concurrency & Overselling', link: '/system-design/14.8-consistency-and-concurrency' },
            { text: '14.9 Reliability & Resilience', link: '/system-design/14.9-reliability-and-resilience' },
            { text: '14.10 API Design & Rate Limiting', link: '/system-design/14.10-api-design-and-rate-limiting' },
            { text: '14.11 Security Architecture', link: '/system-design/14.11-security-architecture' },
            { text: '14.12 Search & Anomaly Detection', link: '/system-design/14.12-search-and-ai-architecture' },
            { text: '14.13 Real-Time Systems', link: '/system-design/14.13-real-time-systems' },
            { text: '14.14 Observability & Telemetry', link: '/system-design/14.14-observability-and-operations' },
            { text: '14.15 Performance Engineering', link: '/system-design/14.15-performance-engineering' },
            { text: '14.16 Cost Modeling & Trade-Offs', link: '/system-design/14.16-cost-and-trade-offs' },
            { text: '14.17 Classic System Design Problems', link: '/system-design/14.17-classic-system-design' },
            { text: 'Architecture Decisions (ADR Log)', link: '/system-design/decisions' }
          ]
        },
        {
          text: 'Interview & Quality Verification',
          items: [
            { text: 'Technical Interview Q&A (150+)', link: '/09-interview-qa' },
            { text: 'Gaps & Roadmap Improvements', link: '/10-gaps-and-improvements' },
            { text: 'Technical Glossary', link: '/11-glossary' },
            { text: 'Items to Confirm With Developer', link: '/12-confirm-list' },
            { text: 'Master Checklist (All 275 Items)', link: '/13-master-checklist' },
            { text: 'Say It Out Loud: Spoken Scripts', link: '/14-say-it-out-loud' }
          ]
        }
      ],
      search: {
        provider: 'local'
      },
      outline: [2, 3]
    },
    mermaid: {
      theme: 'dark'
    },
    vite: {
      optimizeDeps: {
        include: ['mermaid', 'fastdom', 'fastdom/extensions/fastdom-promised.js']
      },
      ssr: {
        noExternal: ['mermaid', 'vitepress-plugin-mermaid', 'fastdom']
      }
    }
  })
);
