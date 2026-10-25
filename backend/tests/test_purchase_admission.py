import pytest
from flow.waiting_room import WaitingRoomManager
from clock import DeterministicClock

def test_FLS_065_purchase_admission():
    """
    FLS-065: Purchase admission.
    Validates token issuance, verification, per-user binding, time-bounded leases,
    and single-use consumption.
    """
    clock = DeterministicClock(initial_timestamp=1700000000.0)
    manager = WaitingRoomManager(clock=clock)

    # 1. Enqueue buyer and admit
    manager.join_queue("user-adm-1", "sku-sale-1")
    admissions = manager.admit_batch("sku-sale-1", batch_size=1, lease_seconds=60)
    assert len(admissions) == 1
    token = admissions[0]["admission_token"]
    assert token.startswith("adm_")

    # 2. Verify admission with correct user -> valid
    ok, msg = manager.verify_admission("user-adm-1", token)
    assert ok is True
    assert "valid" in msg.lower()

    # 3. Verification with different user -> rejected (token bound to specific user)
    ok_imposter, msg_imposter = manager.verify_admission("imposter-user", token)
    assert ok_imposter is False
    assert "does not belong" in msg_imposter

    # 4. Verification with garbage token -> rejected
    ok_bad, _ = manager.verify_admission("user-adm-1", "adm_fake_random")
    assert ok_bad is False

    # 5. Lease expiration: advance clock beyond 60s lease
    clock.advance(65.0)
    ok_expired, msg_expired = manager.verify_admission("user-adm-1", token)
    assert ok_expired is False
    assert "expired" in msg_expired.lower()

    # 6. Single-use consumption test
    manager.join_queue("user-adm-2", "sku-sale-1")
    adm2 = manager.admit_batch("sku-sale-1", batch_size=1, lease_seconds=120)
    tok2 = adm2[0]["admission_token"]

    assert manager.consume_admission("user-adm-2", tok2) is True
    # Subsequent attempt to reuse token fails
    assert manager.consume_admission("user-adm-2", tok2) is False
