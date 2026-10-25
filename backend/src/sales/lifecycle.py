"""
Sale State Machine and Lifecycle Management (FLS-013, FLS-016).
Table-driven state transitions with strict illegal transition rejection and clock-driven lifecycle.
"""

from enum import Enum
from typing import Dict, Set, Tuple, Optional
from clock import Clock

class SaleState(str, Enum):
    DRAFT = "DRAFT"
    SCHEDULED = "SCHEDULED"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"

# Table of strictly valid state transitions
VALID_SALE_TRANSITIONS: Dict[SaleState, Set[SaleState]] = {
    SaleState.DRAFT: {SaleState.SCHEDULED, SaleState.CANCELLED},
    SaleState.SCHEDULED: {SaleState.ACTIVE, SaleState.CANCELLED},
    SaleState.ACTIVE: {SaleState.PAUSED, SaleState.ENDED},
    SaleState.PAUSED: {SaleState.ACTIVE, SaleState.ENDED, SaleState.CANCELLED},
    SaleState.ENDED: set(),       # Terminal state
    SaleState.CANCELLED: set()    # Terminal state
}

class SaleStateMachine:
    """
    Sale state machine enforcing valid state transitions (FLS-016).
    """
    def __init__(self, initial_state: SaleState = SaleState.DRAFT):
        self.state = initial_state

    def can_transition(self, target_state: SaleState) -> bool:
        allowed = VALID_SALE_TRANSITIONS.get(self.state, set())
        return target_state in allowed

    def transition(self, target_state: SaleState) -> Tuple[bool, str]:
        if not self.can_transition(target_state):
            return False, f"Illegal sale state transition from {self.state.value} to {target_state.value}"
        self.state = target_state
        return True, f"Transitioned to {self.state.value}"

class SaleLifecycleManager:
    """
    Clock-driven Sale Lifecycle Manager (FLS-013).
    Evaluates campaign start/end times and stock exhaustion to manage sale status.
    """
    def __init__(
        self,
        campaign_id: str,
        start_time: float,
        end_time: float,
        clock: Optional[Clock] = None,
        initial_state: SaleState = SaleState.SCHEDULED
    ):
        if end_time <= start_time:
            raise ValueError("end_time must be strictly after start_time")
        self.campaign_id = campaign_id
        self.start_time = start_time
        self.end_time = end_time
        self.clock = clock or Clock()
        self.state_machine = SaleStateMachine(initial_state=initial_state)

    @property
    def current_state(self) -> SaleState:
        return self.state_machine.state

    def evaluate_lifecycle(self, available_stock: int) -> SaleState:
        """
        Advances or ends sale lifecycle based on current time and stock.
        """
        now = self.clock.now()

        # If scheduled and start_time has arrived -> activate
        if self.state_machine.state == SaleState.SCHEDULED and now >= self.start_time and now < self.end_time:
            self.state_machine.transition(SaleState.ACTIVE)

        # If active and end_time reached or stock exhausted -> end
        if self.state_machine.state == SaleState.ACTIVE:
            if now >= self.end_time or available_stock <= 0:
                self.state_machine.transition(SaleState.ENDED)

        return self.state_machine.state
