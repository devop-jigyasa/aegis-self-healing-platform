"""
AEGIS Circuit Breaker & Safety Guardrail
Prevents remediation flapping, cascading crashes, and infinite retry loops.
Implements a finite state machine: CLOSED, OPEN, and HALF_OPEN.
"""

import time
from enum import Enum
from typing import Dict, Tuple, Any


class CircuitState(str, Enum):
    CLOSED = "CLOSED"          # Normal operation: automated remediations allowed
    OPEN = "OPEN"              # Tripped: threshold breached or cooldown active, actions halted
    HALF_OPEN = "HALF_OPEN"    # Probe state: trial canary action permitted after window expiry


class RemediationCircuitBreaker:
    def __init__(self, max_attempts: int = 3, window_seconds: int = 600, cooldown_seconds: int = 25):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        # Key: resource_id (e.g. "production-apps/aegis-core") -> list of attempt timestamps
        self.history: Dict[str, list] = {}
        self.last_action_time: Dict[str, float] = {}

    def get_state(self, resource_id: str) -> CircuitState:
        """Determines the current state of the circuit breaker for a given resource."""
        now = time.time()
        attempts = [t for t in self.history.get(resource_id, []) if now - t < self.window_seconds]
        self.history[resource_id] = attempts
        last_time = self.last_action_time.get(resource_id, 0.0)

        # 1. If attempts in the sliding window exceed threshold, circuit is tripped OPEN
        if len(attempts) >= self.max_attempts:
            return CircuitState.OPEN

        # 2. If inside cooldown period immediately following an action, state is OPEN
        if now - last_time < self.cooldown_seconds and last_time > 0:
            return CircuitState.OPEN

        # 3. If cooldown has elapsed after previous actions but window has not expired
        if len(attempts) > 0 and now - last_time >= self.cooldown_seconds:
            return CircuitState.HALF_OPEN

        # 4. Otherwise state is CLOSED (nominal)
        return CircuitState.CLOSED

    def can_remediate(self, resource_id: str) -> Tuple[bool, str]:
        """Checks if a remediation action is safe to execute."""
        now = time.time()
        state = self.get_state(resource_id)
        last_time = self.last_action_time.get(resource_id, 0.0)
        time_since_last = now - last_time

        if state == CircuitState.OPEN:
            attempts = len(self.history.get(resource_id, []))
            if attempts >= self.max_attempts:
                return False, (
                    f"CIRCUIT_TRIPPED: Exceeded {self.max_attempts} attempts within {self.window_seconds}s. "
                    f"Circuit is OPEN. Escalating to human on-call."
                )
            remaining = round(self.cooldown_seconds - time_since_last, 1)
            return False, f"COOLDOWN_ACTIVE: Must wait {remaining}s before retrying {resource_id} (State: OPEN)"

        if state == CircuitState.HALF_OPEN:
            return True, "HALF_OPEN_CANARY_PERMITTED"

        return True, "SAFE"

    def record_attempt(self, resource_id: str):
        """Records an executed remediation attempt."""
        now = time.time()
        if resource_id not in self.history:
            self.history[resource_id] = []
        self.history[resource_id].append(now)
        self.last_action_time[resource_id] = now

    def get_status_payload(self, resource_id: str = "production-apps/aegis-core") -> Dict[str, Any]:
        """Returns structured status payload for observability & debugging."""
        state = self.get_state(resource_id)
        attempts = len(self.history.get(resource_id, []))
        last_time = self.last_action_time.get(resource_id, 0.0)
        return {
            "resource": resource_id,
            "state": state.value,
            "attempts_in_window": attempts,
            "max_attempts": self.max_attempts,
            "window_seconds": self.window_seconds,
            "cooldown_seconds": self.cooldown_seconds,
            "last_action_timestamp": last_time,
            "seconds_since_last_action": round(time.time() - last_time, 1) if last_time > 0 else None,
        }
