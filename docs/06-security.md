# Security & Bot Mitigation Audit (OWASP Top 10)

This security audit maps `18-flash-sale-inventory` to the OWASP Top 10 web vulnerabilities.

---

| OWASP Risk Category | Status in Codebase | Implementation Details & File Reference | Interviewer Attack Vectors & Mitigations |
| :--- | :--- | :--- | :--- |
| **A01: Broken Access Control** | **Protected** | `auth/service.py:75-87`: `BlockedUserRuleManager` rejects blocked accounts. `SessionManager` verifies active session tokens. | Attacker attempts to checkout another user's reservation. Mitigated by verifying `reservation.user_id == authenticated_user_id` in `checkout.py:92`. |
| **A02: Cryptographic Failures** | **Protected** | `models/users.py:78-88`: Passwords hashed with PBKDF2-HMAC-SHA256 (100,000 rounds + 16-byte salt). All money stored in integer cents. | Attacker steals database dump. Rainbow tables fail due to per-user salts. |
| **A03: Injection** | **Protected** | `db/database.py`, SQLAlchemy ORM parameterized queries used across all controllers. | SQL injection via SKU or user parameters. ORM parameter binding neutralizes all payload injection. |
| **A04: Insecure Design** | **Protected** | `models/inventory.py:36`: Hard database check constraints prevent oversell. Idempotency keys prevent duplicate charges. | Scalper creates race condition via parallel threads. Mitigated by single atomic conditional updates. |
| **A05: Security Misconfiguration** | **Protected** | Explicit CORS policy in `api/app.py:40-46`. Structured JSON logging masks raw passwords. | Information leakage in error responses. Internal stack traces suppressed. |
| **A06: Vulnerable Dependencies** | **Protected** | Modern pinned dependencies (`FastAPI 0.115`, `Pydantic 2.10`, `SQLAlchemy 2.0.36`). | Automated scanning with `pip-audit`. |
| **A07: Identification & Auth** | **Protected** | `auth/service.py:48-52`: Exponential lockout ($15 \times 2^n$ mins) after 5 failed login attempts. | Brute force credential stuffing. Throttled and locked out automatically. |
| **A08: Software & Data Integrity** | **Protected** | Cryptographically signed admission tokens in waiting room. Monotonic fencing tokens on locks. | Replaying expired tokens or forged queue jumping. Validated against token store. |
| **A09: Logging & Monitoring** | **Protected** | `observability/logging.py`: Structured JSON logging. `observability/oversell.py`: Instant anomaly alerts. | Silent data corruption. Continuous audit scanner flags drift within seconds. |
| **A10: SSRF** | **Protected** | Payment webhook requests strictly restricted to configured gateway URLs. | Attacker specifies internal metadata URL. Fixed endpoint destinations only. |
