# 📑 SRE Incident Post-Mortem: INC-4922

| Attribute | Value |
| :--- | :--- |
| **Incident ID** | `INC-4922` |
| **Severity Level** | **SEV-2 (Process Instability & Error Surge)** |
| **Affected Workload** | `production-apps/aegis-core` |
| **Target Deployment** | `Deployment/aegis-core` (2 Replicas) |
| **Failure Classification** | `PodCrashLoopBackOff` (Exit Code `1`) |
| **Trigger Mechanism** | Unhandled Process SIGABRT / Panic via Chaos Cockpit |
| **Remediation Strategy** | Autonomous Pod Rollout Patch via `restartedAt` Annotation & Quorum Verification |
| **Circuit Breaker Status** | `CLOSED` (Attempt `2/3` in 600s sliding window) |
| **Benchmarked MTTR** | **18.2 Seconds** (Trigger to 100% Probes Verified) |
| **Resolution Status** | **RESOLVED (Autonomous Closed-Loop)** |

---

## 📌 Executive Summary

On October 20, 2026, at 14:42:15 UTC, the `aegis-core` workload experienced an unhandled runtime exception and fatal process termination (`SIGABRT`, exit code `1`). Upon initial container death, `kubelet` attempted an immediate local restart; however, corrupted thread state induced a secondary restart within 30 seconds, triggering an impending **`CrashLoopBackOff`** condition.

The **AEGIS Autonomous SRE Controller** resolved the failure pattern automatically:
1. Intercepted the Prometheus `CrashLoopBackOff` early-warning alert.
2. Queried the Distributed Circuit Breaker guardrail (Action count: `2/3`, cooldown elapsed: `1,453s`, state: `CLOSED`).
3. Injected a cryptographic timestamp annotation (`kubectl.kubernetes.io/restartedAt: 2026-10-20T14:42:25Z`) into the Deployment PodTemplateSpec, forcing a clean, graceful rolling replacement.
4. Leveraged rolling update constraints (`maxSurge: 1`, `maxUnavailable: 0`) to maintain uninterrupted service quorum.
5. Continuously polled the `/healthz` and `/ready` probes of the new replacement pods until 100% quorum availability was confirmed.

Total Mean Time to Recovery (MTTR) was benchmarked at **18.2 seconds**, restoring the cluster to full health without manual operational toil.

---

## 📊 Detection Telemetry & PromQL Rules

### Prometheus Alert Rule Triggered
```yaml
- alert: CrashLoopBackOffDetected
  expr: rate(kube_pod_container_status_restarts_total{namespace="production-apps", container="aegis-core"}[5m]) * 60 > 2
  for: 5s
  labels:
    severity: critical
    tier: production
  annotations:
    summary: "Rapid container restart flapping detected"
    description: "Container aegis-core restarted >2 times in 5m. Autonomous rollout patch initiated."
```

### Telemetry Signals at Incident Inception
* **Restart Velocity:** `2 restarts in 35 seconds`
* **Pod Status:** `CrashLoopBackOff`
* **Last Termination Reason:** `Error` (`exit_code: 1`)
* **Readiness Status:** `ContainersNotReady (0/1)`

---

## ⏱️ Chronological Incident Timeline

```text
[T+00.00s] 14:42:15.200 - Fatal SIGABRT chaos trigger dispatched to /chaos/crashloop endpoint.
[T+01.40s] 14:42:16.600 - Main process exits with code 1. Kubelet increments restart counter.
[T+05.80s] 14:42:21.000 - Secondary restart fails. Backoff timer increases to 20 seconds.
[T+07.10s] 14:42:22.300 - Prometheus evaluates restart rate > 2 restarts/min; alert CrashLoopBackOffDetected fires.
[T+08.90s] 14:42:24.100 - Alertmanager dispatches incident payload to AEGIS Controller webhook.
[T+09.80s] 14:42:25.000 - AEGIS Controller intercepts webhook:
                          • Workload: production-apps/aegis-core
                          • Target Action: Rolling Rollout Restart
[T+10.40s] 14:42:25.600 - Circuit Breaker Audit:
                          • Action count in 10m window: 2/3 (SAFE)
                          • Cooldown period since INC-4921: > 25s (CLEARED)
                          • Circuit State: CLOSED (Remediation Approved)
[T+11.20s] 14:42:26.400 - K8s API Client patches deployment template:
                          • kubectl.kubernetes.io/restartedAt: 2026-10-20T14:42:26Z
[T+13.10s] 14:42:28.300 - Kubernetes ReplicaSet controller spins up new pod instance aegis-core-84b7f-m12kq.
[T+15.70s] 14:42:30.900 - New pod container initializes; liveness probe returns HTTP 200 OK.
[T+17.00s] 14:42:32.200 - Readiness probe returns HTTP 200; old flapping pod gracefully terminated via SIGTERM.
[T+18.20s] 14:42:33.400 - Active Probe Poller confirms 2/2 pods healthy and ready.
                          • Incident INC-4922 marked RESOLVED.
                          • Benchmark MTTR recorded: 18.2s.
```

---

## 🔍 Root Cause Analysis (5 Whys)

1. **Why was the pod in CrashLoopBackOff?**  
   The application process failed repeatedly on startup, triggering Kubernetes exponential backoff delays.
2. **Why did the process fail on startup?**  
   An uncaught fatal error corrupted the local thread state, leading to immediate process abortion.
3. **Why didn't local kubelet restarts work?**  
   Kubelet restart policy only restarts the existing container on the same host node without flushing local process state or resetting deployment-level ReplicaSet state.
4. **How did the rolling restart resolve it?**  
   Triggering a controlled rolling rollout instantiated a clean container in a fresh Linux namespace, terminating the corrupted pod only after the new replica passed readiness probes.
5. **How were upstream users protected?**  
   Because `maxUnavailable: 0` was enforced, the service never dipped below quorum, maintaining 100% traffic availability throughout remediation.

---

## 🛡️ Circuit Breaker & Safety Audit

```text
┌────────────────────────────────────────────────────────┐
│ CIRCUIT BREAKER AUDIT RECORD                           │
├──────────────────────────┬─────────────────────────────┤
│ Resource Evaluated       │ production-apps/aegis-core  │
│ Sliding Window           │ 600 seconds (10 minutes)    │
│ Registered Actions       │ 2 / 3 Maximum               │
│ Action State             │ APPROVED                    │
│ Cooldown Enforced        │ 25.0 seconds                │
│ Control Plane Flapping   │ FALSE (Stable)              │
│ Circuit State Post-Event │ CLOSED                      │
└──────────────────────────┴─────────────────────────────┘
```

---

## 📈 Post-Remediation Verification & Telemetry

```text
$ kubectl rollout status deployment/aegis-core -n production-apps
deployment "aegis-core" successfully rolled out

$ kubectl get pods -n production-apps -l app=aegis-core
NAME                          READY   STATUS    RESTARTS   AGE
aegis-core-84b7f9411-m12kq    1/1     Running   0          48s
aegis-core-84b7f9411-v78kp    1/1     Running   0          52s

$ curl -s http://localhost:8080/metrics | grep aegis_remediation_actions_total
aegis_remediation_actions_total{action="rolling_restart",status="success"} 1
aegis_remediation_actions_total{action="patch_memory_limits",status="success"} 1
```

* **Service Quorum:** 2/2 Replicas healthy and in `Running` state with 0 restarts.
* **HTTP Latency SLA:** p99 response duration remained `< 12ms`.
* **RCA Artifact:** Persisted to repository incident archive and dashboard event stream.
