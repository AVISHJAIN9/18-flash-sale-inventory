import pytest
from flow.waiting_room import WaitingRoomManager, QueueStatus
from clock import DeterministicClock

def test_FLS_078_virtual_waiting_room():
    """
    FLS-078: Virtual waiting room.
    Verifies that incoming traffic is placed in an ordered waiting room,
    monitored for queue volume, and controlled via batch admissions.
    """
    clock = DeterministicClock(initial_time=1700000000.0)
    manager = WaitingRoomManager(clock=clock)

    # 1. 10 buyers enter the waiting room for a limited sneaker drop
    for i in range(10):
        res = manager.join_queue(f"user-{i}", "sku-sneaker-rare")
        assert res["status"] == QueueStatus.QUEUED.value
        assert res["position"] == i + 1

    status = manager.get_queue_status("sku-sneaker-rare")
    assert status["queued_count"] == 10
    assert status["admitted_active_count"] == 0

    # 2. Virtual waiting room admits a controlled batch of 3 users
    admitted = manager.admit_batch("sku-sneaker-rare", batch_size=3, lease_seconds=180)
    assert len(admitted) == 3
    assert [a["user_id"] for a in admitted] == ["user-0", "user-1", "user-2"]

    status2 = manager.get_queue_status("sku-sneaker-rare")
    assert status2["queued_count"] == 7
    assert status2["admitted_active_count"] == 3

    # 3. Next batch admits 2 more users (FIFO preservation)
    admitted2 = manager.admit_batch("sku-sneaker-rare", batch_size=2, lease_seconds=180)
    assert len(admitted2) == 2
    assert [a["user_id"] for a in admitted2] == ["user-3", "user-4"]

    status3 = manager.get_queue_status("sku-sneaker-rare")
    assert status3["queued_count"] == 5
    assert status3["admitted_active_count"] == 5
