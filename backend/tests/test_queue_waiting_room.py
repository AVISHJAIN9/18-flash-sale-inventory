import pytest
from flow.waiting_room import WaitingRoomManager, QueueStatus
from clock import DeterministicClock

def test_FLS_066_queue_waiting_room():
    """
    FLS-066: Queue/waiting room.
    Validates FIFO ordering, position tracking, queue length monitoring,
    idempotent queue entry, and stale admission sweeping.
    """
    clock = DeterministicClock(initial_timestamp=1700000000.0)
    manager = WaitingRoomManager(clock=clock)

    # 1. Multiple buyers join queue
    t1 = manager.join_queue("buyer-1", "sku-flash-shoe")
    assert t1["position"] == 1
    assert t1["status"] == QueueStatus.QUEUED.value

    t2 = manager.join_queue("buyer-2", "sku-flash-shoe")
    assert t2["position"] == 2

    t3 = manager.join_queue("buyer-3", "sku-flash-shoe")
    assert t3["position"] == 3

    # 2. Queue status check
    st = manager.get_queue_status("sku-flash-shoe")
    assert st["queued_count"] == 3
    assert st["admitted_active_count"] == 0

    # 3. Duplicate join returns existing position (idempotent enqueue)
    t1_dup = manager.join_queue("buyer-1", "sku-flash-shoe")
    assert t1_dup["ticket_id"] == t1["ticket_id"]
    assert t1_dup["position"] == 1

    # 4. Admit top 2 users (FIFO: buyer-1, buyer-2 admitted; buyer-3 remains in queue)
    admitted = manager.admit_batch("sku-flash-shoe", batch_size=2, lease_seconds=100)
    assert len(admitted) == 2
    assert admitted[0]["user_id"] == "buyer-1"
    assert admitted[1]["user_id"] == "buyer-2"

    # Status after admission: 1 in queue, 2 active admitted
    st2 = manager.get_queue_status("sku-flash-shoe")
    assert st2["queued_count"] == 1
    assert st2["admitted_active_count"] == 2

    # 5. Expire stale admissions after time passes
    clock.advance(150.0)
    expired_cnt = manager.expire_stale_admissions()
    assert expired_cnt == 2

    st3 = manager.get_queue_status("sku-flash-shoe")
    assert st3["admitted_active_count"] == 0
    assert st3["queued_count"] == 1
