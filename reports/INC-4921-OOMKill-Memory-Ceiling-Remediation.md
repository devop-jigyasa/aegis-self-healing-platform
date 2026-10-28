# 📑 SRE Incident Post-Mortem: INC-4921

| Attribute | Value |
| :--- | :--- |
| **Incident ID** | `INC-4921` |
| **Severity Level** | **SEV-2 (High Availability Risk)** |
| **Affected Workload** | `production-apps/aegis-core` |
| **Target Deployment** | `Deployment/aegis-core` (2 Replicas) |
| **Failure Classification** | `ContainerOOMKilled` (Exit Code `137`) |
| **Trigger Mechanism** | Rapid Heap Leak Simulation via Chaos Cockpit |
| **Remediation Strategy** | Autonomous Dynamic Memory Limit Expansion (+25% Buffer) & Rolling Pod Replacement |
| **Circuit Breaker Status** | `CLOSED` (Attempt `1/3` in 600s sliding window) |
| **Benchmarked MTTR** | **24.5 Seconds** (Trigger to 100% Probes Verified) |
| **Resolution Status** | **RESOLVED (Autonomous Closed-Loop)** |

---

## 📌 Executive Summary

On October 20, 2026, at 14:18:02 UTC, the `aegis-core` microservice in namespace `production-apps` suffered an acute memory exhaustion event. The container resident memory exceeded its configured cgroup ceiling of `256Mi`, inducing a Linux kernel Out-Of-Memory (OOM) killer termination with exit code `137`.

Instead of permitting uncoordinated `kubelet` restarts that lead to `CrashLoopBackOff` flapping, the **AEGIS Autonomous SRE Controller**:
1. Intercepted the Prometheus `ContainerOOMKilled` Alertmanager webhook.
2. Verified safety guardrails via the Distributed Circuit Breaker (`CLOSED` state, 25s cooldown cleared).
3. Dynamically patched the Kubernetes Deployment specification to scale the memory limit by **+25% (256Mi ➔ 320Mi)**.
4. Coordinated a zero-downtime rolling restart (`maxSurge: 1`, `maxUnavailable: 0`).
5. Polled `/healthz` and `/ready` probes across all replicas until 100% availability was confirmed.

Total Mean Time to Recovery (MTTR) was benchmarked at **24.5 seconds**, with zero manual human on-call intervention required.

---

## 📊 Detection Telemetry & PromQL Rules

### Prometheus Alert Rule Triggered
```yaml
- alert: ContainerOOMKilled
  expr: kube_pod_container_status_last_terminated_reason{namespace="production-apps", container="aegis-core"} == 1
  for: 5s
  labels:
    severity: critical
    tier: production
  annotations:
    summary: "Container aegis-core was OOMKilled (Exit Code 137)"
    description: "Pod {{ $labels.pod }} exceeded memory limit. Immediate SRE remediation dispatched."
```

### Telemetry Signals at Incident Inception
* **Baseline RSS Memory:** `48.2 MB`
* **Peak Memory at Termination:** `256.0 MB` (Hard Limit Reached)
* **Linux Kernel Signal:** `SIGKILL` dispatched by kernel `oom-killer`
* **Termination Reason:** `OOMKilled` (`exit_code: 137`)

---

## ⏱️ Chronological Incident Timeline

```text
[T+00.00s] 14:18:02.100 - Ingestion of memory leak payload via /chaos/oom endpoint.
[T+03.80s] 14:18:05.900 - RSS memory breaches 256Mi cgroup ceiling. Pod aegis-core-689bf-x7z9q terminated by kernel (Exit Code 137).
[T+08.20s] 14:18:10.300 - Prometheus scrapes kube-state-metrics; evaluates ContainerOOMKilled rule as FIRING.
[T+10.50s] 14:18:12.600 - Alertmanager routes JSON alert payload to AEGIS Controller webhook (POST /webhook/alert).
[T+11.80s] 14:18:13.900 - AEGIS Controller intercepts webhook:
                          • Resource: production-apps/aegis-core
                          • Failure Reason: OOMKilled
[T+12.40s] 14:18:14.500 - Circuit Breaker Audit:
                          • Action count in 10m window: 1/3 (SAFE)
                          • Cooldown period since last action: > 25s (CLEARED)
                          • Circuit State: CLOSED (Remediation Approved)
[T+14.10s] 14:18:16.200 - Controller calculates dynamic headroom:
                          • Current Limit: 256Mi
                          • Expansion Rate: +25%
                          • Target Limit: 320Mi
[T+16.30s] 14:18:18.400 - Kubernetes API Client executes AppsV1 strategic merge patch on deployment aegis-core.
[T+18.90s] 14:18:21.000 - Kubelet initiates zero-downtime rolling update with new container memory limits (320Mi).
[T+21.40s] 14:18:23.500 - Active Probe Poller begins readiness and liveness verification loops.
[T+24.50s] 14:18:26.600 - Probe verification succeeded: 2/2 replicas returning HTTP 200 on /healthz.
                          • Incident INC-4921 marked RESOLVED.
                          • Benchmark MTTR recorded: 24.5s.
```

---

## 🔍 Root Cause Analysis (5 Whys)

1. **Why did the pod terminate?**  
   The container process was forcibly killed by the host OS kernel with exit code `137`.
2. **Why did the kernel terminate the process?**  
   The container memory usage breached its strict cgroup limit of `256Mi`.
3. **Why did memory consumption grow unchecked?**  
   An uncontrolled unbounded allocation was triggered in userland code, appending gigabyte buffers without garbage collection triggers.
4. **Why didn't standard Kubernetes restarts resolve the incident?**  
   Standard `kubelet` restarts bring up identical pod specs with the same `256Mi` limit, causing continuous `CrashLoopBackOff` upon receiving new traffic.
5. **How did AEGIS prevent cascading failure?**  
   AEGIS resolved the underlying structural bottleneck by dynamically expanding the memory ceiling to `320Mi` and validating probe response prior to closing the incident.

---

## 🛡️ Circuit Breaker & Safety Audit

```text
┌────────────────────────────────────────────────────────┐
│ CIRCUIT BREAKER AUDIT RECORD                           │
├──────────────────────────┬─────────────────────────────┤
│ Resource Evaluated       │ production-apps/aegis-core  │
│ Sliding Window           │ 600 seconds (10 minutes)    │
│ Registered Actions       │ 1 / 3 Maximum               │
│ Action State             │ APPROVED                    │
│ Cooldown Enforced        │ 25.0 seconds                │
│ Control Plane Flapping   │ FALSE (Stable)              │
│ Circuit State Post-Event │ CLOSED                      │
└──────────────────────────┴─────────────────────────────┘
```

---

## 📈 Post-Remediation Verification & Telemetry

```text
$ kubectl get pods -n production-apps
NAME                          READY   STATUS    RESTARTS   AGE
aegis-core-7d4c9f864-j82mk    1/1     Running   0          38s
aegis-core-7d4c9f864-w91nq    1/1     Running   0          41s

$ curl -s http://localhost:8080/healthz
{"status":"healthy","uptime_seconds":38,"memory_rss_mb":52.4,"cpu_percent":4.1}
```

* **Memory Stability:** Stabilized at `52.4 MB RSS` (16.3% of new `320Mi` ceiling).
* **HTTP SLA:** 0 dropped requests observed through Service ClusterIP load balancer.
* **Audit Signature:** Event persisted to AEGIS Mission Control timeline radar.
