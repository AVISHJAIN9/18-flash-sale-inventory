# Items Requiring Developer Confirmation [CONFIRM WITH DEVELOPER]

The following architectural parameters and operational thresholds are derived from code inspection and should be verified with the lead developer:

1. `[CONFIRM WITH DEVELOPER]`: Confirm that the default reservation hold lease of **300 seconds (5 minutes)** meets business requirements for checkout completion.
2. `[CONFIRM WITH DEVELOPER]`: Confirm whether the token bucket default burst capacity of **50 tokens** and refill rate of **20 tokens/sec** in `flow/throttling.py` aligns with production edge CDN rules.
3. `[CONFIRM WITH DEVELOPER]`: Confirm whether maximum discount caps default to **90.0%** across all promotional campaigns in `pricing/promotions.py`.
4. `[CONFIRM WITH DEVELOPER]`: Confirm whether the account lockout cool-down base of **15 minutes** with a max of 5 failed login attempts meets enterprise compliance standards.
5. `[CONFIRM WITH DEVELOPER]`: Confirm that the documented scheduled activation tolerance threshold of **<= 1.0 second** is acceptable under multi-region clock drift.
