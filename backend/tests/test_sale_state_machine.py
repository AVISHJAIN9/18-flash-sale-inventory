import pytest
from sales.lifecycle import SaleStateMachine, SaleState, VALID_SALE_TRANSITIONS

def test_FLS_016_sale_state_machine():
    # 1. Test valid transitions sequence: DRAFT -> SCHEDULED -> ACTIVE -> PAUSED -> ACTIVE -> ENDED
    sm = SaleStateMachine(initial_state=SaleState.DRAFT)

    ok1, msg1 = sm.transition(SaleState.SCHEDULED)
    assert ok1 is True
    assert sm.state == SaleState.SCHEDULED

    ok2, msg2 = sm.transition(SaleState.ACTIVE)
    assert ok2 is True
    assert sm.state == SaleState.ACTIVE

    ok3, msg3 = sm.transition(SaleState.PAUSED)
    assert ok3 is True
    assert sm.state == SaleState.PAUSED

    ok4, msg4 = sm.transition(SaleState.ACTIVE)
    assert ok4 is True
    assert sm.state == SaleState.ACTIVE

    ok5, msg5 = sm.transition(SaleState.ENDED)
    assert ok5 is True
    assert sm.state == SaleState.ENDED

    # 2. Table-driven test: every transition NOT in VALID_SALE_TRANSITIONS must be rejected!
    for source in SaleState:
        for target in SaleState:
            machine = SaleStateMachine(initial_state=source)
            allowed = target in VALID_SALE_TRANSITIONS.get(source, set())
            ok, err = machine.transition(target)
            if allowed:
                assert ok is True
                assert machine.state == target
            else:
                assert ok is False
                assert "Illegal sale state transition" in err
                assert machine.state == source
