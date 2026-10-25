import pytest
from flow.waiting_room import WaitingRoomManager
from clock import DeterministicClock

def test_FLS_080_queue_tokens():
    """
    FLS-080: Queue tokens.
    Verifies generation of cryptographically signed HMAC queue tokens,
    successful validation of authentic tokens, rejection of tampered tokens,
    and expiration handling.
    """
    clock = DeterministicClock(initial_time=1700000000.0)
    manager = WaitingRoomManager(clock=clock)

    q_res = manager.join_queue("buyer-tokenized", "sku-phone-tok")
    ticket_id = q_res["ticket_id"]

    secret = "production_super_secret_signing_key_42"

    # 1. Generate authentic signed queue token
    qtok = manager.generate_queue_token(ticket_id, secret=secret, ttl_seconds=300)
    assert qtok.startswith("qtok_")

    # 2. Verify authentic token -> valid
    valid, msg, payload = manager.verify_queue_token(qtok, secret=secret)
    assert valid is True
    assert payload["ticket_id"] == ticket_id
    assert payload["user_id"] == "buyer-tokenized"
    assert payload["sku_id"] == "sku-phone-tok"

    # 3. Verify with wrong secret key -> fails verification (signature mismatch)
    valid_bad_secret, msg_bad, _ = manager.verify_queue_token(qtok, secret="wrong_secret_key")
    assert valid_bad_secret is False
    assert "tampered" in msg_bad.lower() or "failed" in msg_bad.lower()

    # 4. Verify tampered payload -> fails verification
    parts = qtok.split(".")
    tampered_tok = parts[0] + "xyz." + parts[1]
    valid_tampered, _, _ = manager.verify_queue_token(tampered_tok, secret=secret)
    assert valid_tampered is False

    # 5. Token expiration check
    clock.advance(350.0)
    valid_expired, msg_exp, _ = manager.verify_queue_token(qtok, secret=secret)
    assert valid_expired is False
    assert "expired" in msg_exp.lower()
