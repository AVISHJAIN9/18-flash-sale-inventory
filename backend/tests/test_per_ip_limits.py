import pytest
from flow.waiting_room import WaitingRoomManager
from clock import DeterministicClock

def test_FLS_085_per_ip_limits():
    """
    FLS-085: Per-IP limits.
    Enforces per-IP sliding window rate limits, allowing traffic under the quota,
    blocking excessive calls, and resetting once the sliding window has elapsed.
    """
    clock = DeterministicClock(initial_time=1700000000.0)
    manager = WaitingRoomManager(clock=clock)

    ip_normal = "192.168.1.50"
    ip_bot = "203.0.113.99"

    # 1. Normal traffic within limit (max 5 requests per 30s)
    for i in range(5):
        allowed, count = manager.check_ip_limit(ip_normal, max_requests=5, window_seconds=30.0)
        assert allowed is True
        assert count == i + 1

    # 6th request from normal IP exceeds limit -> blocked!
    allowed, count = manager.check_ip_limit(ip_normal, max_requests=5, window_seconds=30.0)
    assert allowed is False
    assert count == 5

    # 2. Independent tracking: bot IP is tracked separately from normal IP
    allowed_bot, count_bot = manager.check_ip_limit(ip_bot, max_requests=5, window_seconds=30.0)
    assert allowed_bot is True
    assert count_bot == 1

    # 3. Sliding window expiration: advance clock past 30s window
    clock.advance(35.0)

    # Normal IP can now make requests again
    allowed_after, count_after = manager.check_ip_limit(ip_normal, max_requests=5, window_seconds=30.0)
    assert allowed_after is True
    assert count_after == 1
