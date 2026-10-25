"""
Tests for Queue, Fairness & Anti-Bot:
- FLS-081: Queue expiration
- FLS-082: Fair queue ordering
- FLS-084: Randomized admission (statistical uniformity over N >= 10,000 draws)
- FLS-086: Per-account limits
"""

import pytest
import math
from clock import Clock
from flow.waiting_room import WaitingRoomManager, QueueStatus


def test_FLS_081_queue_expiration():
    """
    FLS-081: Queue expiration (BE, P1).
    Verifies:
    - Tickets queued longer than max_queue_age_seconds expire and are removed
    - Admitted tickets exceeding lease TTL are pruned from active admission pool
    """
    clock = Clock(initial_time=1000.0)
    mgr = WaitingRoomManager(clock=clock)

    # 1. Join 3 users
    mgr.join_queue("user-exp-1", "sku-exp-item")
    clock.advance(100.0)  # t=1100.0
    mgr.join_queue("user-exp-2", "sku-exp-item")
    clock.advance(100.0)  # t=1200.0
    mgr.join_queue("user-exp-3", "sku-exp-item")

    # Admit user-exp-1 with lease_seconds=60 (expires at 1260.0)
    admitted = mgr.admit_batch("sku-exp-item", batch_size=1, lease_seconds=60)
    assert len(admitted) == 1
    assert admitted[0]["user_id"] == "user-exp-1"

    # Advance clock to 1500.0
    # user-exp-1 lease expired (1260 < 1500)
    # user-exp-2 queued for 400s (joined at 1100, now 1500)
    # user-exp-3 queued for 300s (joined at 1200, now 1500)
    clock.advance(300.0)  # t=1500.0

    # Prune tickets older than 350s
    expired_ids = mgr.expire_stale_tickets("sku-exp-item", max_queue_age_seconds=350.0)
    # user-exp-1 (admitted lease expired) and user-exp-2 (queued 400s > 350s) must expire
    assert len(expired_ids) == 2

    # user-exp-3 remains active in queue
    status_3 = mgr.join_queue("user-exp-3", "sku-exp-item")
    assert status_3["status"] == QueueStatus.QUEUED.value
    assert status_3["position"] == 1


def test_FLS_082_fair_queue_ordering():
    """
    FLS-082: Fair queue ordering (BE, P1).
    Verifies:
    - FIFO admission order strictly matches arrival order
    - No starvation or queue-jumping
    """
    clock = Clock(initial_time=2000.0)
    mgr = WaitingRoomManager(clock=clock)

    users = [f"fifo-buyer-{i}" for i in range(10)]
    for u in users:
        mgr.join_queue(u, "sku-fair-queue")
        clock.advance(1.0)

    # Admit in two batches of 5
    batch1 = mgr.admit_batch("sku-fair-queue", batch_size=5)
    batch2 = mgr.admit_batch("sku-fair-queue", batch_size=5)

    admitted_order = [t["user_id"] for t in batch1] + [t["user_id"] for t in batch2]
    assert admitted_order == users, "Queue admission did not preserve strict FIFO fair ordering"


def test_FLS_084_randomized_admission_uniformity():
    """
    FLS-084: Randomized admission (BE, P1).
    Verifies (§9 Invariant):
    - Randomized admission is statistically uniform over N >= 10,000 draws
    - Chi-squared goodness-of-fit test confirms no bot or bias favoring early/late slots
    """
    import random as py_random
    rng = py_random.Random(42)  # Deterministic seed for reproducible test

    N_DRAWS = 10_000
    NUM_BUCKETS = 10
    counts = {i: 0 for i in range(NUM_BUCKETS)}

    # Perform 10,000 independent lottery draws
    for _ in range(N_DRAWS):
        mgr = WaitingRoomManager()
        # Create pool of 10 participants
        for i in range(NUM_BUCKETS):
            mgr.join_queue(f"candidate-{i}", "sku-lottery")
        # Draw 1 winner
        winners = mgr.randomized_admit_draw("sku-lottery", num_to_admit=1, rng=rng)
        assert len(winners) == 1
        winner_id = int(winners[0]["user_id"].split("-")[-1])
        counts[winner_id] += 1

    expected_per_bucket = N_DRAWS / NUM_BUCKETS  # 1,000
    # Chi-squared statistic: sum((observed - expected)^2 / expected)
    chi_square = sum(((count - expected_per_bucket) ** 2) / expected_per_bucket for count in counts.values())

    # For 9 degrees of freedom, critical value at alpha=0.01 is 21.666
    # Any chi_square < 21.67 indicates statistical uniformity consistent with uniform distribution
    assert chi_square < 21.67, f"Lottery distribution failed uniformity check: chi_square={chi_square:.2f}, counts={counts}"

    # Verify each bucket is within 4 standard deviations (sigma = sqrt(10000 * 0.1 * 0.9) = 30)
    for i, count in counts.items():
        diff = abs(count - expected_per_bucket)
        assert diff <= 120, f"Bucket {i} with {count} draws deviated excessively from expected {expected_per_bucket}"


def test_FLS_086_per_account_limits():
    """
    FLS-086: Per-account limits (BE, P1).
    Verifies (§9 Invariant):
    - Account cannot hold multiple simultaneous active queue tickets for the same SKU
    - Re-entering the queue returns the existing ticket position rather than spawning duplicates
    """
    clock = Clock(initial_time=5000.0)
    mgr = WaitingRoomManager(clock=clock)

    # 1. First queue entry succeeds
    tkt1 = mgr.join_queue("scalper-bot-account", "sku-exclusive-drop")
    assert tkt1["status"] == QueueStatus.QUEUED.value
    assert tkt1["position"] == 1

    # 2. Check account limit rejects duplicate active attempt
    allowed, reason = mgr.check_account_limit("scalper-bot-account", "sku-exclusive-drop")
    assert allowed is False
    assert "already has an active queue ticket" in reason

    # 3. Second join_queue idempotent returns existing ticket instead of duplicate queue position
    tkt2 = mgr.join_queue("scalper-bot-account", "sku-exclusive-drop")
    assert tkt2["ticket_id"] == tkt1["ticket_id"]
    assert tkt2["position"] == 1
