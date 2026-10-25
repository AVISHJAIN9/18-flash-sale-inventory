import pytest
from flow.waiting_room import WaitingRoomManager
from clock import DeterministicClock

def test_FLS_079_queue_position():
    """
    FLS-079: Queue position.
    Verifies dynamic queue position calculation, users ahead count,
    and estimated wait time based on throughput rate.
    """
    clock = DeterministicClock(initial_time=1700000000.0)
    manager = WaitingRoomManager(clock=clock)

    # 4 users join queue
    manager.join_queue("buyer-pos-1", "sku-concert-tix")
    manager.join_queue("buyer-pos-2", "sku-concert-tix")
    manager.join_queue("buyer-pos-3", "sku-concert-tix")
    manager.join_queue("buyer-pos-4", "sku-concert-tix")

    # 1. Check user 3's position
    # Position: 3, Users ahead: 2.
    # At rate of 0.5 admissions/sec (1 every 2 seconds): estimated wait = 2 / 0.5 = 4 seconds
    p3 = manager.get_user_position("buyer-pos-3", "sku-concert-tix", admission_rate_per_sec=0.5)
    assert p3["in_queue"] is True
    assert p3["position"] == 3
    assert p3["users_ahead"] == 2
    assert p3["estimated_wait_seconds"] == 4

    # 2. Admit the top 2 users
    manager.admit_batch("sku-concert-tix", batch_size=2)

    # 3. Position for user 3 now advances from 3 to 1 (users ahead: 0, wait: 0)
    p3_updated = manager.get_user_position("buyer-pos-3", "sku-concert-tix", admission_rate_per_sec=0.5)
    assert p3_updated["in_queue"] is True
    assert p3_updated["position"] == 1
    assert p3_updated["users_ahead"] == 0
    assert p3_updated["estimated_wait_seconds"] == 0

    # 4. Position for already-admitted user 1 returns in_queue=False
    p1 = manager.get_user_position("buyer-pos-1", "sku-concert-tix")
    assert p1["in_queue"] is False
    assert p1["status"] == "ADMITTED"
