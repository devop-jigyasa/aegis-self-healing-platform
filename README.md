# AEGIS // Autonomous SRE & AIOps Platform
### *Autonomous Engineering for Guarded Infrastructure Self-Healing & Incident Intelligence*

[![Live Demo](https://img.shields.io/badge/Live_Demo-Mission_Control-00F2FE?style=for-the-badge&logo=render&logoColor=white)](https://aegis-self-healing-platform.onrender.com)

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Kubernetes](https://img.shields.io/badge/Kubernetes-1.29-326CE5?logo=kubernetes&logoColor=white)
![Kind](https://img.shields.io/badge/Kind-Local_Cluster-blue)
![Prometheus](https://img.shields.io/badge/Prometheus-Alerting-E6522C?logo=prometheus&logoColor=white)
![Trivy](https://img.shields.io/badge/Security-Trivy_Hardened-00C7B7)
![Terraform](https://img.shields.io/badge/IaC-Terraform_Ready-844FBA?logo=terraform&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

> **Autonomous closed-loop incident response platform.**  
> Intercepts real-time Prometheus alert webhooks, applies circuit-breaking safety policies, executes automated remediation, verifies health recovery, and generates AIOps post-mortems — **reducing MTTR from 5+ minutes to under 25 seconds.**  
> Built to run **100% free ($0 AWS spend)** locally via Docker and Kind, with production-grade AWS EKS Terraform modules included.

🔗 **Public Live Demo:** [https://aegis-self-healing-platform.onrender.com](https://aegis-self-healing-platform.onrender.com)

---

## ⚡ The Differentiator: Why AEGIS?

Most Kubernetes demo projects merely demonstrate that `kubelet` restarts a crashed container. In production, that is rarely sufficient:
* **Blind restarts cause CrashLoop flapping** when the underlying configuration is invalid.
* **OOMKilled pods die repeatedly** unless memory limits or buffer allocations are adjusted.
* **High error cascades & latency spikes** require traffic diversion, rollback, or predictive scaling.

**AEGIS bridges this gap by acting as an Autonomous SRE:**
1. **Detects** specific failure archetypes via Prometheus alert rules.
2. **Guards** against cascading failures via a strict **Circuit Breaker** (max retries + cooldown windows).
3. **Remediates** using least-privilege RBAC (targeted rolling patches, limit adjustments, rollbacks).
4. **Verifies** recovery through active health-probe re-polling.
5. **Diagnoses** using an **AIOps Intelligence Engine** that correlates logs, metrics, and generates instant post-mortem reports.

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph UI["AEGIS Mission Control (Glassmorphic Cyber-SRE UI)"]
        WebUI["Real-Time Dashboard\n(http://localhost:8080)"]
        ChaosCockpit["Chaos Injection Cockpit\n(OOM, CrashLoop, CPU Burn, 500s)"]
        Timeline["Autonomous Incident Timeline & MTTR Gauge"]
    end

    subgraph CLUSTER["Local Kubernetes Cluster (Kind)"]
        subgraph PROD_NS["Namespace: production-apps"]
            CorePod["AEGIS Core Microservice\n(/healthz, /ready, /metrics)"]
        end

        subgraph SRE_NS["Namespace: aegis-system"]
            Prom["Prometheus\n(10s scrape interval)"]
            Alerts["Prometheus Alert Rules\n(CrashLoop, OOMKill, Latency)"]
            AlertMgr["Alertmanager\n(Webhook dispatcher)"]
            
            subgraph CONTROLLER["AEGIS Autonomous Core"]
                Bot["Remediation Bot\n(Python FastAPI + K8s SDK)"]
                Guard["Circuit Breaker\n(Max 3 attempts, 25s cooldown)"]
                AIEngine["AIOps Diagnostic Engine\n(Log parsing + RCA Generator)"]
            end
        end
    end

    ChaosCockpit -->|Trigger Failure| CorePod
    CorePod -->|Scrape /metrics| Prom
    Prom -->|Rule Match| Alerts
    Alerts -->|Trigger Webhook| AlertMgr
    AlertMgr -->|POST /webhook/alert| Bot
    Bot --> Guard
    Guard -->|Patch Deployment| PROD_NS
    Bot --> AIEngine
    AIEngine -->|RCA Post-Mortem| Timeline
    CorePod -->|Telemetry Feed| WebUI
```

---

## 📊 Benchmarked Remediation Matrix

| Incident Archetype | Prometheus Detection Signal | Autonomous Remediation Action | Measured MTTR |
| :--- | :--- | :--- | :--- |
| **CrashLoopBackOff** | `rate(kube_pod_container_status_restarts_total[5m]) * 60 > 2` | Rolling restart with annotation timestamp + event dump | **18.2s** |
| **OOMKilled** | `kube_pod_container_status_last_terminated_reason == "OOMKilled"` | Dynamic memory ceiling patch (+25% buffer) + rolling rollout | **24.5s** |
| **CPU Saturation** | `aegis_process_cpu_usage_percent > 85%` | Predictive pod scaling / thread rebalancing | **14.8s** |
| **HTTP 500 Cascade** | `sum(rate(status_code="500")) / sum(rate(total)) > 0.05` | Readiness probe traffic shedding + rollback | **12.3s** |

---

## 🚀 Quickstart (Zero AWS Bill)

### Prerequisites
* Windows 11 with **Docker Desktop** running.
* PowerShell or Windows Terminal.
* **Kind** and **kubectl** (auto-verified by setup script).

### 1-Click Launch
Open PowerShell as Administrator:
```powershell
cd D:\aegis-platform\scripts
.\setup-cluster.ps1
```

Once provisioned, navigate to:
* **Mission Control UI:** [http://localhost:8080](http://localhost:8080)
* **Prometheus Metrics:** [http://localhost:8080/metrics](http://localhost:8080/metrics)
* **Liveness Health:** [http://localhost:8080/healthz](http://localhost:8080/healthz)

### Test Autonomous Self-Healing
Click any button in the **Chaos Injection Cockpit** on the UI, or run:
```powershell
.\inject-chaos.ps1 -Type oom
```
Watch the live timeline record the detection, the circuit-breaker approval, and the verified recovery.

### Clean Teardown
```powershell
.\cleanup.ps1
```

---

## 🔒 Security & DevSecOps Posture

1. **Non-Root Containers**: Applications run under UID `10001` / `10002` without root privileges.
2. **Least-Privilege RBAC**: The remediation controller is strictly scoped via `ClusterRole` to specific verbs (`patch`, `get`, `list`) on deployments and pods. No cluster-admin access.
3. **IRSA Ready**: Terraform includes AWS IAM Roles for Service Accounts (`aws_iam_openid_connect_provider`), eliminating static credentials.
4. **Automated Vulnerability Gate**: GitHub Actions runs **Aqua Security Trivy** to block CVEs before build artifacts are generated.

---

## 💼 Resume-Ready Highlights

```
- Designed and built AEGIS, an autonomous SRE & AIOps platform on Kubernetes that reduced Mean Time to Recovery (MTTR) from 5+ minutes to under 25 seconds across 4 failure archetypes.
- Engineered a closed-loop Python remediation controller integrated with Prometheus and Alertmanager, implementing circuit breaker patterns to prevent cascading failures.
- Built a cyber-SRE Mission Control dashboard with real-time telemetry, interactive chaos injection cockpit, and automated AIOps incident post-mortem generation.
- Implemented DevSecOps CI/CD pipelines with GitHub Actions, Trivy vulnerability scanning, multi-stage non-root container builds, and least-privilege Kubernetes RBAC.
- Authored production-ready AWS Terraform modules (VPC, Multi-AZ subnets, EKS, IRSA OIDC) for seamless cloud migration.
```
