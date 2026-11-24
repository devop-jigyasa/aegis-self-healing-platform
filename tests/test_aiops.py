import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "controller")))

from aiops_engine import AIOpsDiagnosticEngine  # noqa: E402


def test_aiops_engine_signature_matching():
    engine = AIOpsDiagnosticEngine()
    report = engine.analyze_incident(
        alert_name="AegisContainerOOMKilled",
        resource_name="aegis-core",
        namespace="production-apps",
        logs="Container exceeded memory limit. Killed by kernel: MemoryError.",
        metrics={"alert_severity": "critical", "mttr": 21.4},
        remediation_action="OOM_RESOURCE_BUFFER_RESTART",
        mttr_seconds=21.4,
    )
    assert "incident_id" in report
    assert report["mttr_seconds"] == 21.4
    assert "Heap exhaustion" in report["post_mortem_md"]


def test_aiops_crashloop_signature():
    engine = AIOpsDiagnosticEngine()
    report = engine.analyze_incident(
        alert_name="AegisPodCrashLooping",
        resource_name="aegis-core",
        namespace="production-apps",
        logs="Process crashed unexpectedly with exit code 1.",
        metrics={"alert_severity": "critical", "mttr": 18.2},
        remediation_action="ROLLING_RESTART",
        mttr_seconds=18.2,
    )
    assert "Fatal process exit" in report["post_mortem_md"]
    assert report["alert_name"] == "AegisPodCrashLooping"
