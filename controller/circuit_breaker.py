"""
AEGIS Circuit Breaker & Safety Guardrail
Prevents remediation flapping, cascading crashes, and infinite retry loops.
"""

import time
from typing import Dict, Any, Tuple


class RemediationCircuitBreaker:
    def __init__(self, max_attempts: int = 3, window_seconds: int = 600, cooldown_seconds: int = 30):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds
        # Key: resource_id (e.g. "default/deployment/aegis-core") -> list of attempt timestamps
        self.history: Dict[str, list] = {}
        self.last_action_time: Dict[str, float] = {}

    def can_remediate(self, resource_id: str) -> Tuple[bool, str]:
        """Checks if a remediation action is safe to execute."""
        now = time.time()

        # Check cooldown
        last_time = self.last_action_time.get(resource_id, 0.0)
        time_since_last = now - last_time
        if time_since_last < self.cooldown_seconds:
            remaining = round(self.cooldown_seconds - time_since_last, 1)
            return False, f"COOLDOWN_ACTIVE: Must wait {remaining}s before retrying {resource_id}"

        # Clean history older than window
        attempts = [t for t in self.history.get(resource_id, []) if now - t < self.window_seconds]
        self.history[resource_id] = attempts

        # Check max attempts limit
        if len(attempts) >= self.max_attempts:
            return False, f"CIRCUIT_TRIPPED: Exceeded {self.max_attempts} attempts within {self.window_seconds}s. Escalating to human on-call."

        return True, "SAFE"

    def record_attempt(self, resource_id: str):
        """Records a successful or executed remediation attempt."""
        now = time.time()
        if resource_id not in self.history:
            self.history[resource_id] = []
        self.history[resource_id].append(now)
        self.last_action_time[resource_id] = now
