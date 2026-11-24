"""
AEGIS Core Microservice
High-reliability demo application with built-in Prometheus telemetry,
dynamic health/readiness probes, and controlled failure/chaos simulation.
"""

import os
import time
import socket
import asyncio
import threading
from typing import List
import psutil

from fastapi import FastAPI, Response, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

app = FastAPI(
    title="AEGIS Core Microservice",
    description="Mission-critical cloud-native service with telemetry and chaos hooks",
    version="1.0.0",
)

# --- Enable Cross-Origin Resource Sharing (CORS) with Explicit Production Origins ---
ALLOWED_ORIGINS = [
    "https://aegis-self-healing-platform-static.vercel.app",
    "https://aegis-self-healing-platform.onrender.com",
    "http://localhost:8080",
    "http://localhost:8000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- State Management & Chaos Flags ---
SERVICE_START_TIME = time.time()
HOSTNAME = socket.gethostname()
CHAOS_ENABLED = os.getenv("CHAOS_ENABLED", "true").lower() == "true"
CHAOS_SECRET = os.getenv("CHAOS_SECRET")
_memory_hog: List[bytearray] = []
_chaos_state = {
    "is_healthy": True,
    "is_ready": True,
    "cpu_stress_active": False,
    "artificial_latency_sec": 0.0,
    "memory_leak_mb": 0,
    "simulated_errors": False,
}

# --- Prometheus Metrics ---
REQUEST_COUNT = Counter(
    "aegis_http_requests_total",
    "Total incoming HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "aegis_http_request_duration_seconds",
    "Histogram of request processing latencies",
    buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)
ACTIVE_CHAOS = Gauge(
    "aegis_active_chaos_incidents",
    "Gauge representing the count of actively injected chaos simulations",
)
MEMORY_USAGE_MB = Gauge(
    "aegis_process_memory_usage_mb",
    "Resident Set Size (RSS) memory consumption in megabytes",
)
CPU_USAGE_PERCENT = Gauge(
    "aegis_process_cpu_usage_percent",
    "Process CPU utilization percentage",
)
REMEDIATION_ACTIONS_TOTAL = Counter(
    "aegis_remediation_actions_total",
    "Total count of autonomous remediation actions by type and status",
    ["action_type", "status"],
)

# System and probe endpoints that must never be disrupted by application chaos (Defect B5)
PROBE_AND_SYSTEM_ENDPOINTS = {"/healthz", "/ready", "/metrics", "/api/status", "/api/circuit-breaker"}


@app.middleware("http")
async def monitor_requests(request, call_next):
    start_time = time.time()
    endpoint = request.url.path

    # P3 Item 23 Fix: Enforce authentication and environment guardrails on chaos endpoints
    if endpoint.startswith("/chaos"):
        if not CHAOS_ENABLED:
            return Response(
                content='{"error": "Forbidden: Chaos engineering endpoints disabled (CHAOS_ENABLED=false)"}',
                status_code=403,
                media_type="application/json",
            )
        if CHAOS_SECRET:
            token = request.headers.get("X-Chaos-Secret") or request.headers.get("Authorization")
            expected_bearer = f"Bearer {CHAOS_SECRET}"
            if token != CHAOS_SECRET and token != expected_bearer:
                return Response(
                    content='{"error": "Unauthorized: Invalid or missing X-Chaos-Secret"}',
                    status_code=401,
                    media_type="application/json",
                )

    # Defect B5 Fix: Ensure health and observability probes bypass synthetic chaos simulation
    if endpoint not in PROBE_AND_SYSTEM_ENDPOINTS and not endpoint.startswith("/chaos"):
        # Injected non-blocking latency simulation (Defect B4 Fix)
        if _chaos_state["artificial_latency_sec"] > 0:
            await asyncio.sleep(_chaos_state["artificial_latency_sec"])

        # Injected 500 cascade simulation
        if _chaos_state["simulated_errors"]:
            REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code=500).inc()
            return Response(
                content='{"error": "Simulated Chaos HTTP 500 Cascade"}',
                status_code=500,
                media_type="application/json",
            )

    response = await call_next(request)
    duration = time.time() - start_time

    # Record Prometheus metrics
    REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code=response.status_code).inc()
    REQUEST_LATENCY.observe(duration)
    return response


# --- Background Telemetry Thread ---
def _telemetry_updater():
    process = psutil.Process(os.getpid())
    while True:
        try:
            mem_info = process.memory_info()
            rss_mb = mem_info.rss / (1024 * 1024)
            cpu_pct = process.cpu_percent(interval=0.5)

            MEMORY_USAGE_MB.set(round(rss_mb, 2))
            CPU_USAGE_PERCENT.set(round(cpu_pct, 2))

            chaos_count = sum(
                [
                    not _chaos_state["is_healthy"],
                    not _chaos_state["is_ready"],
                    _chaos_state["cpu_stress_active"],
                    _chaos_state["artificial_latency_sec"] > 0,
                    _chaos_state["memory_leak_mb"] > 0,
                    _chaos_state["simulated_errors"],
                ]
            )
            ACTIVE_CHAOS.set(chaos_count)
        except Exception:
            pass
        time.sleep(1.5)


telemetry_thread = threading.Thread(target=_telemetry_updater, daemon=True)
telemetry_thread.start()


# --- Health & Readiness Probes ---
@app.get("/healthz")
def healthz():
    if not _chaos_state["is_healthy"]:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unhealthy: Injected Liveness Failure")
    return {"status": "HEALTHY", "uptime_sec": round(time.time() - SERVICE_START_TIME, 2), "node": HOSTNAME}


@app.get("/ready")
def ready():
    if not _chaos_state["is_ready"]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Not Ready: Injected Readiness Failure")
    return {"status": "READY", "node": HOSTNAME}


# --- Circuit Breaker API Endpoint ---
@app.get("/api/circuit-breaker")
def get_circuit_breaker():
    """Returns the circuit breaker status payload for the production workload."""
    import urllib.request
    import json
    controller_url = "http://aegis-controller.aegis-system.svc.cluster.local:5000/api/circuit-breaker"
    try:
        req = urllib.request.Request(controller_url, headers={"User-Agent": "aegis-core"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return {
            "resource": "production-apps/aegis-core",
            "state": "CLOSED",
            "attempts_in_window": 0,
            "max_attempts": 3,
            "window_seconds": 600,
            "cooldown_seconds": 25,
            "last_action_timestamp": 0.0,
            "seconds_since_last_action": None,
            "mode": "autonomous-guardrail",
        }


# --- Chaos Simulation Control Endpoints ---
@app.post("/chaos/oom")
def trigger_oom(megabytes: int = 120):
    global _memory_hog
    chunk = bytearray(megabytes * 1024 * 1024)
    _memory_hog.append(chunk)
    _chaos_state["memory_leak_mb"] += megabytes
    return {"status": "INJECTED", "type": "OOM_LEAK", "allocated_mb": megabytes, "total_leaked_mb": _chaos_state["memory_leak_mb"]}


@app.post("/chaos/crash")
def trigger_crash():
    def _delayed_suicide():
        time.sleep(0.5)
        os._exit(1)

    threading.Thread(target=_delayed_suicide, daemon=True).start()
    return {"status": "KILLING_PROCESS", "signal": "SIGKILL (exit 1)", "simulating": "CrashLoopBackOff"}


@app.post("/chaos/cpu")
def trigger_cpu_burn(duration_sec: int = 15):
    _chaos_state["cpu_stress_active"] = True

    def _burn():
        end_time = time.time() + duration_sec
        while time.time() < end_time:
            _ = [x**2 for x in range(5000)]
        _chaos_state["cpu_stress_active"] = False

    threading.Thread(target=_burn, daemon=True).start()
    return {"status": "INJECTED", "type": "CPU_BURN", "duration_sec": duration_sec}


@app.post("/chaos/latency")
def trigger_latency(seconds: float = 2.5):
    _chaos_state["artificial_latency_sec"] = seconds
    return {"status": "INJECTED", "type": "ARTIFICIAL_LATENCY", "delay_seconds": seconds}


@app.post("/chaos/errors")
def trigger_errors(enable: bool = True):
    _chaos_state["simulated_errors"] = enable
    return {"status": "INJECTED", "type": "CASCADE_500", "active": enable}


@app.post("/chaos/unhealthy")
def trigger_unhealthy(enable: bool = True):
    _chaos_state["is_healthy"] = not enable
    return {"status": "INJECTED", "type": "LIVENESS_FAILURE", "healthy": _chaos_state["is_healthy"]}


@app.post("/chaos/unready")
def trigger_unready(enable: bool = True):
    _chaos_state["is_ready"] = not enable
    return {"status": "INJECTED", "type": "READINESS_FAILURE", "ready": _chaos_state["is_ready"]}


@app.post("/chaos/reset")
def reset_chaos():
    global _memory_hog
    _memory_hog.clear()
    _chaos_state["is_healthy"] = True
    _chaos_state["is_ready"] = True
    _chaos_state["cpu_stress_active"] = False
    _chaos_state["artificial_latency_sec"] = 0.0
    _chaos_state["memory_leak_mb"] = 0
    _chaos_state["simulated_errors"] = False
    return {"status": "CLEARED", "system_state": "NOMINAL"}


@app.get("/api/status")
def get_status():
    process = psutil.Process(os.getpid())
    return {
        "service": "AEGIS Core Service",
        "hostname": HOSTNAME,
        "pid": os.getpid(),
        "uptime_seconds": round(time.time() - SERVICE_START_TIME, 1),
        "memory_mb": round(process.memory_info().rss / (1024 * 1024), 2),
        "cpu_percent": round(process.cpu_percent(interval=None), 2),
        "chaos_state": _chaos_state,
        "system_cores": psutil.cpu_count(),
        "timestamp": time.time(),
    }


@app.get("/metrics")
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- Static Dashboard Mounting ---
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def serve_dashboard():
        index_file = os.path.join(static_dir, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return "<h3>AEGIS Dashboard Index Missing</h3>"

    @app.get("/style.css")
    def serve_css():
        return FileResponse(os.path.join(static_dir, "style.css"))

    @app.get("/app.js")
    def serve_js():
        return FileResponse(os.path.join(static_dir, "app.js"))
