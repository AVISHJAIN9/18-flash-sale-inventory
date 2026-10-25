import pytest
from clock import Clock
from sales.lifecycle import SaleLifecycleManager, SaleState

def test_FLS_013_sale_lifecycle_management():
    # Campaign from T=100 to T=200
    clk = Clock(initial_time=50.0)
    mgr = SaleLifecycleManager(campaign_id="c-live-1", start_time=100.0, end_time=200.0, clock=clk)

    # At T=50: Before start_time -> SCHEDULED
    assert mgr.evaluate_lifecycle(available_stock=50) == SaleState.SCHEDULED

    # Advance clock to T=100: start_time arrives -> becomes ACTIVE
    clk.set_time(100.0)
    assert mgr.evaluate_lifecycle(available_stock=50) == SaleState.ACTIVE

    # At T=150 with stock remaining -> stays ACTIVE
    clk.set_time(150.0)
    assert mgr.evaluate_lifecycle(available_stock=20) == SaleState.ACTIVE

    # Stock drops to 0 at T=160 -> sale automatically ENDS!
    assert mgr.evaluate_lifecycle(available_stock=0) == SaleState.ENDED

    # New campaign to test time-based ending
    clk2 = Clock(initial_time=100.0)
    mgr2 = SaleLifecycleManager(campaign_id="c-live-2", start_time=100.0, end_time=200.0, clock=clk2)
    assert mgr2.evaluate_lifecycle(available_stock=100) == SaleState.ACTIVE

    # Advance past end_time (T=201) with stock remaining -> ENDS due to time expiry!
    clk2.set_time(201.0)
    assert mgr2.evaluate_lifecycle(available_stock=50) == SaleState.ENDED
