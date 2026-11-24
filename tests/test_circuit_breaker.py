import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "controller")))

from circuit_breaker import RemediationCircuitBreaker, CircuitState  # noqa: E402


def test_circuit_breaker_initial_state():
    cb = RemediationCircuitBreaker(max_attempts=3, window_seconds=600, cooldown_seconds=2)
    res = "production-apps/aegis-core"
    assert cb.get_state(res) == CircuitState.CLOSED
    can_proceed, reason = cb.can_remediate(res)
    assert can_proceed is True
    assert reason == "SAFE"


def test_circuit_breaker_cooldown_rejection():
    cb = RemediationCircuitBreaker(max_attempts=3, window_seconds=600, cooldown_seconds=5)
    res = "production-apps/aegis-core"
    cb.record_attempt(res)
    assert cb.get_state(res) == CircuitState.OPEN
    can_proceed, reason = cb.can_remediate(res)
    assert can_proceed is False
    assert "COOLDOWN_ACTIVE" in reason


def test_circuit_breaker_max_attempts_trip():
    cb = RemediationCircuitBreaker(max_attempts=3, window_seconds=600, cooldown_seconds=0)
    res = "production-apps/aegis-core"
    cb.record_attempt(res)
    cb.record_attempt(res)
    cb.record_attempt(res)
    can_proceed, reason = cb.can_remediate(res)
    assert can_proceed is False
    assert "CIRCUIT_TRIPPED" in reason


def test_circuit_breaker_status_payload():
    cb = RemediationCircuitBreaker(max_attempts=3, window_seconds=600, cooldown_seconds=25)
    payload = cb.get_status_payload("production-apps/aegis-core")
    assert payload["resource"] == "production-apps/aegis-core"
    assert payload["state"] == "CLOSED"
    assert payload["max_attempts"] == 3
    assert payload["window_seconds"] == 600
