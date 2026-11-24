"""
AEGIS Autonomous Remediation Controller
Receives Prometheus Alertmanager webhooks, enforces circuit breaking policies,
triggers bounded Kubernetes remediation actions, verifies health, and records MTTR.
"""

import os
import re
import json
import time
import hmac
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

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

# Prometheus Telemetry Counter (Item 15)
REMEDIATION_COUNTER = Counter(
    "aegis_remediation_actions_total",
    "Total automated remediation actions executed by AEGIS controller",
    ["action_type", "status", "target_deployment"]
)

# P3 Item 23: Shared secret for Alertmanager webhook authentication
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET")

# Defect B3 Fix: Ensure reports directory is in a writable location for non-root containers
REPORTS_DIR = os.environ.get("REPORTS_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "reports"))
if not os.path.isabs(REPORTS_DIR) or not os.access(os.path.dirname(REPORTS_DIR) or ".", os.W_OK):
    REPORTS_FILE = os.path.join(REPORTS_DIR, "incidents.json")
else:
    REPORTS_FILE = os.path.join(REPORTS_DIR, "incidents.json")

# Fallback writable path for strict read-only non-root container filesystems
FALLBACK_REPORTS_FILE = "/tmp/aegis-incidents.json"

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
    """Persists incident records for auditing and MTTR benchmarking (Defect B3 Fix)."""
    target_path = REPORTS_FILE
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
    except Exception:
        target_path = FALLBACK_REPORTS_FILE

    try:
        reports = []
        if os.path.exists(target_path):
            with open(target_path, "r") as f:
                try:
                    reports = json.load(f)
                except Exception:
                    reports = []
        reports.append(report_data)
        with open(target_path, "w") as f:
            json.dump(reports, f, indent=2)
        logger.info(f"Persisted incident report {report_data.get('incident_id')} to {target_path}")
    except Exception as e:
        logger.error(f"Failed to save incident report: {e}")


def _resolve_target_deployment(namespace: str, target_name: str) -> str:
    """Defect B6 Fix: Resolves a pod or raw label to its parent Deployment before patching."""
    if not apps_v1:
        return target_name

    # Check if target_name is already a valid deployment
    try:
        apps_v1.read_namespaced_deployment(name=target_name, namespace=namespace)
        return target_name
    except Exception:
        pass

    # If not a deployment, try resolving pod ownerReferences
    if core_v1:
        try:
            pod = core_v1.read_namespaced_pod(name=target_name, namespace=namespace)
            if pod.metadata.owner_references:
                for ref in pod.metadata.owner_references:
                    if ref.kind == "ReplicaSet":
                        rs_name = ref.name
                        # Standard K8s deployment creates RS formatted as <deployment>-<hash>
                        dep_name = rs_name.rsplit("-", 1)[0]
                        return dep_name
                    elif ref.kind == "Deployment":
                        return ref.name
        except Exception:
            pass

    return "aegis-core"


def _fetch_pod_logs(namespace: str, deployment_name: str) -> str:
    """Captures recent logs/stderr from the target deployment pods using CoreV1Api."""
    if not core_v1:
        return f"[LOGS] Simulated diagnostic trace for {namespace}/{deployment_name} (CoreV1Api unavailable)"

    try:
        pods = core_v1.list_namespaced_pod(namespace=namespace, label_selector=f"app={deployment_name}")
        if not pods.items:
            pods = core_v1.list_namespaced_pod(namespace=namespace)
            matched = [p for p in pods.items if deployment_name in p.metadata.name]
            if matched:
                pods.items = matched

        if pods.items:
            target_pod = pods.items[0].metadata.name
            try:
                raw_logs = core_v1.read_namespaced_pod_log(name=target_pod, namespace=namespace, tail_lines=50, previous=True)
            except Exception:
                raw_logs = core_v1.read_namespaced_pod_log(name=target_pod, namespace=namespace, tail_lines=50)
            return raw_logs
    except Exception as e:
        logger.warning(f"Could not retrieve pod logs for {deployment_name}: {e}")

    return f"Container logs captured for {namespace}/{deployment_name} prior to termination."


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


def _execute_oom_memory_patch(namespace: str, deployment_name: str, buffer_ratio: float = 0.25) -> bool:
    """Dynamically reads the current memory limit and patches it with a +25% buffer to remediate OOMKill."""
    if not apps_v1:
        logger.info(f"[SIMULATION] Dynamic memory limit buffer (+25%) applied for {namespace}/{deployment_name}")
        return True

    try:
        dep = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        containers = dep.spec.template.spec.containers
        if not containers:
            return _execute_k8s_restart(namespace, deployment_name)

        target_container = containers[0]
        current_mem = "256Mi"
        if target_container.resources and target_container.resources.limits:
            current_mem = target_container.resources.limits.get("memory", "256Mi")

        match = re.match(r"^(\d+)([A-Za-z]+)?$", current_mem)
        if match:
            val = int(match.group(1))
            unit = match.group(2) or "Mi"
            new_val = int(val * (1 + buffer_ratio))
            new_mem = f"{new_val}{unit}"
        else:
            new_mem = "320Mi"

        now_str = datetime.utcnow().isoformat() + "Z"
        patch_body = {
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": now_str,
                            "aegis.sre.io/auto-remediated": "OOMKill-Memory-Buffer"
                        }
                    },
                    "spec": {
                        "containers": [
                            {
                                "name": target_container.name,
                                "resources": {
                                    "limits": {"memory": new_mem}
                                }
                            }
                        ]
                    }
                }
            }
        }
        apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch_body)
        logger.info(f"Dynamically upgraded memory limit for {namespace}/{deployment_name} from {current_mem} to {new_mem}")
        return True
    except Exception as e:
        logger.error(f"Failed to patch memory limit for {deployment_name}: {e}. Falling back to standard restart.")
        return _execute_k8s_restart(namespace, deployment_name)


def _execute_cpu_scale_up(namespace: str, deployment_name: str) -> bool:
    """Scales up deployment replicas by +1 to mitigate high CPU load."""
    if not apps_v1:
        logger.info(f"[SIMULATION] Scaled deployment {namespace}/{deployment_name} replicas +1 for CPU load")
        return True

    try:
        dep = apps_v1.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        current_replicas = dep.spec.replicas or 1
        new_replicas = current_replicas + 1
        patch_body = {"spec": {"replicas": new_replicas}}
        apps_v1.patch_namespaced_deployment(name=deployment_name, namespace=namespace, body=patch_body)
        logger.info(f"Scaled deployment {namespace}/{deployment_name} from {current_replicas} to {new_replicas} replicas")
        return True
    except Exception as e:
        logger.error(f"Failed to scale deployment {deployment_name}: {e}. Falling back to restart.")
        return _execute_k8s_restart(namespace, deployment_name)


async def _verify_recovery(namespace: str, deployment_name: str, timeout_sec: int = 45) -> bool:
    """Defect B4 Fix: Non-blocking asynchronous verification of deployment readiness."""
    start = time.time()
    if not apps_v1:
        await asyncio.sleep(2)
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
        await asyncio.sleep(2)

    logger.warning(f"Deployment {deployment_name} failed to achieve healthy ready status within {timeout_sec}s.")
    return False


@app.get("/healthz")
def health():
    return {"status": "HEALTHY", "controller": "AEGIS Autonomous Core"}


@app.get("/api/circuit-breaker")
def get_circuit_breaker_status(resource: str = "production-apps/aegis-core"):
    """Exposes real-time circuit breaker finite state machine data."""
    return circuit_breaker.get_status_payload(resource)


@app.post("/webhook/alert")
async def alertmanager_webhook(request: Request):
    """Webhook listener invoked by Prometheus Alertmanager."""
    if not WEBHOOK_SECRET:
        logger.error("Rejected webhook: WEBHOOK_SECRET environment variable is missing on controller")
        return Response(
            content=json.dumps({"error": "Unauthorized: Controller webhook authentication not configured"}),
            status_code=401,
            media_type="application/json",
        )

    auth_header = request.headers.get("Authorization", "")
    secret_header = request.headers.get("X-Webhook-Secret", "")
    expected_bearer = f"Bearer {WEBHOOK_SECRET}"

    is_valid = False
    if secret_header and hmac.compare_digest(secret_header, WEBHOOK_SECRET):
        is_valid = True
    elif auth_header:
        if hmac.compare_digest(auth_header, WEBHOOK_SECRET) or hmac.compare_digest(auth_header, expected_bearer):
            is_valid = True

    if not is_valid:
        logger.warning("Rejected unauthorized webhook request: missing or invalid secret")
        return Response(
            content=json.dumps({"error": "Unauthorized: Invalid or missing X-Webhook-Secret / Authorization"}),
            status_code=401,
            media_type="application/json",
        )

    alert_start_time = time.time()
    payload = await request.json()
    logger.info(f"Received Alertmanager payload with {len(payload.get('alerts', []))} alert(s)")

    remediation_results = []

    for alert in payload.get("alerts", []):
        alert_name = alert.get("labels", {}).get("alertname", "UnknownAlert")
        namespace = alert.get("labels", {}).get("namespace", "production-apps")
        raw_target = alert.get("labels", {}).get("deployment") or alert.get("labels", {}).get("pod") or "aegis-core"
        severity = alert.get("labels", {}).get("severity", "critical")
        status_state = alert.get("status", "firing")

        # Defect B6 Fix: Resolve raw target label to deployment before recording attempt
        target_deployment = _resolve_target_deployment(namespace, raw_target)
        logger.info(f"Processing alert: {alert_name} | Target: {namespace}/{target_deployment} | State: {status_state}")

        if status_state != "firing":
            continue

        resource_id = f"{namespace}/{target_deployment}"
        can_proceed, reason = circuit_breaker.can_remediate(resource_id)

        if not can_proceed:
            logger.warning(f"Remediation halted by safety policy for {resource_id}: {reason}")
            remediation_results.append({
                "resource": resource_id,
                "status": "CIRCUIT_BREAKER_BLOCKED",
                "reason": reason,
            })
            continue

        # 1. Fetch real pod logs prior to executing remediation
        pod_logs = _fetch_pod_logs(namespace, target_deployment)

        # 2. Execute distinct, target-specific remediation action
        action_name = "ROLLING_RESTART"
        if "OOM" in alert_name:
            action_name = "OOM_RESOURCE_BUFFER_RESTART"
            success = _execute_oom_memory_patch(namespace=namespace, deployment_name=target_deployment)
        elif "CPU" in alert_name:
            action_name = "SCALE_OR_DRAIN"
            success = _execute_cpu_scale_up(namespace=namespace, deployment_name=target_deployment)
        else:
            success = _execute_k8s_restart(namespace=namespace, deployment_name=target_deployment)

        # Record attempt only after successful remediation invocation
        if success:
            circuit_breaker.record_attempt(resource_id)

        # Track metric for Prometheus
        REMEDIATION_COUNTER.labels(
            action_type=action_name,
            status="success" if success else "failed",
            target_deployment=target_deployment
        ).inc()

        # 3. Health verification loop (Non-blocking async - Defect B4 Fix)
        is_healed = False
        mttr = 0.0
        if success:
            is_healed = await _verify_recovery(namespace=namespace, deployment_name=target_deployment)
            mttr = time.time() - alert_start_time

        # 4. Generate AIOps incident diagnosis using real captured logs
        rca_report = aiops_engine.analyze_incident(
            alert_name=alert_name,
            resource_name=target_deployment,
            namespace=namespace,
            logs=pod_logs,
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


@app.get("/metrics")
def metrics():
    """Prometheus telemetry scrape endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/incidents")
def list_incidents():
    """Returns historical incident post-mortems and MTTR benchmarks."""
    for path in [REPORTS_FILE, FALLBACK_REPORTS_FILE]:
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except Exception:
                pass
    return []


if __name__ == "__main__":
    import uvicorn
    # P3 Item 26 Fix: Pure uvicorn runner without reload
    uvicorn.run("remediation_bot:app", host="0.0.0.0", port=5000)
