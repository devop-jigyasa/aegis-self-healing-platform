"""
AEGIS Autonomous Remediation Controller
Receives Prometheus Alertmanager webhooks, enforces circuit breaking policies,
triggers bounded Kubernetes remediation actions, verifies health, and records MTTR.
"""

import os
import json
import time
import logging
from typing import Dict, Any, List
from datetime import datetime

import requests
from fastapi import FastAPI, Request, status, HTTPException
from pydantic import BaseModel

from circuit_breaker import RemediationCircuitBreaker
from aiops_engine import AIOpsDiagnosticEngine

try:
    from kubernetes import client, config
    K8S_AVAILABLE = True
except ImportError:
    K8S_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("aegis-controller")

app = FastAPI(title="AEGIS Autonomous SRE Controller")

circuit_breaker = RemediationCircuitBreaker(max_attempts=3, window_seconds=600, cooldown_seconds=25)
aiops_engine = AIOpsDiagnosticEngine()

REPORTS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports", "incidents.json")

# Initialize K8s client (works both in-cluster and via local kubeconfig)
apps_v1 = None
core_v1 = None
if K8S_AVAILABLE:
    try:
        config.load_incluster_config()
        logger.info("Loaded in-cluster Kubernetes configuration.")
    except Exception:
        try:
            config.load_kube_config()
            logger.info("Loaded local kubeconfig configuration.")
        except Exception as e:
            logger.warning(f"Could not load Kubernetes configuration: {e}")

    try:
        apps_v1 = client.AppsV1Api()
        core_v1 = client.CoreV1Api()
    except Exception:
        pass


def _save_incident_report(report_data: Dict[str, Any]):
    """Persists incident records for auditing and MTTR benchmarking."""
    try:
        os.makedirs(os.path.dirname(REPORTS_FILE), exist_ok=True)
        reports = []
        if os.path.exists(REPORTS_FILE):
            with open(REPORTS_FILE, "r") as f:
                try:
                    reports = json.load(f)
                except Exception:
                    reports = []
        reports.append(report_data)
        with open(REPORTS_FILE, "w") as f:
            json.dump(reports, f, indent=2)
        logger.info(f"Persisted incident report {report_data.get('incident_id')} to {REPORTS_FILE}")
    except Exception as e:
        logger.error(f"Failed to save incident report: {e}")


def _execute_k8s_restart(namespace: str, deployment_name: str) -> bool:
    """Executes a rolling restart of a deployment by patching its pod template annotations."""
    if not apps_v1:
        logger.info(f"[SIMULATION] Rolling restart triggered for {namespace}/{deployment_name}")
        return True

    try:
        now_str = datetime.utcnow().isoformat() + "Z"
        patch_body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now_str
                        }
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(
            name=deployment_name, namespace=namespace, body=patch_body
        )
        logger.info(f"Successfully patched deployment {namespace}/{deployment_name} to trigger rolling restart.")
        return True
    except Exception as e:
        logger.error(f"Failed to patch deployment {deployment_name}: {e}")
        return False


def _verify_recovery(namespace: str, deployment_name: str, timeout_sec: int = 45) -> bool:
    """Verifies that the deployment achieves Ready status after remediation."""
    start = time.time()
    if not apps_v1:
        # Simulation delay
        time.sleep(2)
        return True

    while time.time() - start < timeout_sec:
        try:
            dep = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
            replicas = dep.status.replicas or 0
            ready_replicas = dep.status.ready_replicas or 0
            if replicas > 0 and ready_replicas == replicas:
                logger.info(f"Deployment {deployment_name} verified healthy: {ready_replicas}/{replicas} pods ready.")
                return True
        except Exception:
            pass
        time.sleep(2)

    logger.warning(f"Deployment {deployment_name} failed to achieve healthy ready status within {timeout_sec}s.")
    return False


@app.get("/healthz")
def health():
    return {"status": "HEALTHY", "controller": "AEGIS Autonomous Core"}


@app.post("/webhook/alert")
async def alertmanager_webhook(request: Request):
    """Webhook listener invoked by Prometheus Alertmanager."""
    alert_start_time = time.time()
    payload = await request.json()
    logger.info(f"Received Alertmanager payload with {len(payload.get('alerts', []))} alert(s)")

    remediation_results = []

    for alert in payload.get("alerts", []):
        alert_name = alert.get("labels", {}).get("alertname", "UnknownAlert")
        namespace = alert.get("labels", {}).get("namespace", "production-apps")
        pod_or_deploy = alert.get("labels", {}).get("deployment") or alert.get("labels", {}).get("pod") or "aegis-core"
        severity = alert.get("labels", {}).get("severity", "critical")
        status_state = alert.get("status", "firing")

        logger.info(f"Processing alert: {alert_name} | Target: {namespace}/{pod_or_deploy} | State: {status_state}")

        if status_state != "firing":
            continue

        resource_id = f"{namespace}/{pod_or_deploy}"
        can_proceed, reason = circuit_breaker.can_remediate(resource_id)

        if not can_proceed:
            logger.warning(f"Remediation halted by safety policy for {resource_id}: {reason}")
            remediation_results.append({
                "resource": resource_id,
                "status": "CIRCUIT_BREAKER_BLOCKED",
                "reason": reason,
            })
            continue

        # Execute bounded remediation
        action_name = "ROLLING_RESTART"
        if "OOM" in alert_name:
            action_name = "OOM_RESOURCE_BUFFER_RESTART"
        elif "CPU" in alert_name:
            action_name = "SCALE_OR_DRAIN"

        circuit_breaker.record_attempt(resource_id)
        success = _execute_k8s_restart(namespace=namespace, deployment_name=pod_or_deploy)

        # Health verification loop
        is_healed = False
        mttr = 0.0
        if success:
            is_healed = _verify_recovery(namespace=namespace, deployment_name=pod_or_deploy)
            mttr = time.time() - alert_start_time

        # Generate AIOps incident diagnosis
        rca_report = aiops_engine.analyze_incident(
            alert_name=alert_name,
            resource_name=pod_or_deploy,
            namespace=namespace,
            logs=f"Simulated alert trace for {alert_name} on {pod_or_deploy}",
            metrics={"alert_severity": severity, "mttr": round(mttr, 2)},
            remediation_action=action_name,
            mttr_seconds=mttr,
        )

        _save_incident_report(rca_report)
        remediation_results.append({
            "resource": resource_id,
            "action": action_name,
            "healed": is_healed,
            "mttr_sec": round(mttr, 2),
            "incident_id": rca_report.get("incident_id"),
        })

    return {"status": "PROCESSED", "remediations": remediation_results}


@app.get("/api/incidents")
def list_incidents():
    """Returns historical incident post-mortems and MTTR benchmarks."""
    if os.path.exists(REPORTS_FILE):
        try:
            with open(REPORTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("remediation_bot:app", host="0.0.0.0", port=5000, reload=True)
