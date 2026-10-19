"""
AEGIS Core Microservice
High-reliability demo application with built-in Prometheus telemetry,
dynamic health/readiness probes, and controlled failure/chaos simulation.
"""

import os
import sys
import time
import socket
import threading
from typing import Dict, Any, List
import psutil

from fastapi import FastAPI, Response, status, HTTPException
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

# --- State Management & Chaos Flags ---
SERVICE_START_TIME = time.time()
HOSTNAME = socket.gethostname()
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
    "HTTP request latency in seconds",
    ["endpoint"],
)
ACTIVE_INCIDENTS = Gauge(
    "aegis_active_chaos_incidents",
    "Count of active simulated chaos conditions",
)
MEMORY_USAGE_MB = Gauge(
    "aegis_process_memory_usage_mb",
    "Process resident memory usage in megabytes",
)
CPU_USAGE_PERCENT = Gauge(
    "aegis_process_cpu_usage_percent",
    "Process CPU utilization percentage",
)


@app.middleware("http")
async def monitor_requests(request, call_next):
    start_time = time.time()
    endpoint = request.url.path

    # Apply artificial latency if chaos is active
    if _chaos_state["artificial_latency_sec"] > 0:
        time.sleep(_chaos_state["artificial_latency_sec"])

    # Simulate 500 error if active on general routes
    if _chaos_state["simulated_errors"] and not endpoint.startswith("/chaos"):
        REQUEST_COUNT.labels(method=request.method, endpoint=endpoint, status_code="500").inc()
        return Response(content="Simulated 500 Internal Server Error", status_code=500)

    try:
        response = await call_next(request)
        status_code = str(response.status_code)
    except Exception:
        status_code = "500"
        raise
    finally:
        duration = time.time() - start_time
        REQUEST_COUNT.labels(
            method=request.method, endpoint=endpoint, status_code=status_code
        ).inc()
        REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration)

    return response


# --- Background Telemetry Updater ---
def _update_system_gauges():
    while True:
        try:
            process = psutil.Process(os.getpid())
            mem_mb = process.memory_info().rss / (1024 * 1024)
            cpu_pct = process.cpu_percent(interval=1.0)
            MEMORY_USAGE_MB.set(mem_mb)
            CPU_USAGE_PERCENT.set(cpu_pct)

            active_count = sum(
                1
                for k, v in _chaos_state.items()
                if (k == "is_healthy" and not v)
                or (k == "is_ready" and not v)
                or (k == "cpu_stress_active" and v)
                or (k == "artificial_latency_sec" and v > 0)
                or (k == "memory_leak_mb" and v > 0)
                or (k == "simulated_errors" and v)
            )
            ACTIVE_INCIDENTS.set(active_count)
        except Exception:
            pass
        time.sleep(2)


telemetry_thread = threading.Thread(target=_update_system_gauges, daemon=True)
telemetry_thread.start()


# --- Probes & Telemetry Endpoints ---
@app.get("/healthz")
def liveness_probe():
    """Kubernetes Liveness Probe: restarts pod if status is not 200."""
    if not _chaos_state["is_healthy"]:
        return Response(content='{"status": "FATAL_UNHEALTHY"}', status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    return {"status": "HEALTHY", "uptime_sec": round(time.time() - SERVICE_START_TIME, 2), "node": HOSTNAME}


@app.get("/ready")
def readiness_probe():
    """Kubernetes Readiness Probe: removes pod from service traffic if not 200."""
    if not _chaos_state["is_ready"]:
        return Response(content='{"status": "NOT_READY"}', status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return {"status": "READY", "node": HOSTNAME}


@app.get("/metrics")
def prometheus_metrics():
    """Prometheus Scrape Endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/status")
def system_status() -> Dict[str, Any]:
    """Real-time system telemetry for the Mission Control dashboard."""
    process = psutil.Process(os.getpid())
    return {
        "service": "AEGIS Core Service",
        "hostname": HOSTNAME,
        "pid": os.getpid(),
        "uptime_seconds": round(time.time() - SERVICE_START_TIME, 1),
        "memory_mb": round(process.memory_info().rss / (1024 * 1024), 2),
        "cpu_percent": process.cpu_percent(),
        "chaos_state": _chaos_state,
        "system_cores": psutil.cpu_count(),
        "timestamp": time.time(),
    }


# --- Controlled Chaos & Failure Injection Cockpit ---
@app.post("/chaos/crash")
def chaos_crash():
    """Simulates immediate process crash (CrashLoop simulation)."""
    def _delayed_crash():
        time.sleep(0.5)
        os._exit(1)

    threading.Thread(target=_delayed_crash).start()
    return {"status": "TRIGGERED", "action": "Process exiting in 500ms to trigger container restart"}


@app.post("/chaos/unhealthy")
def chaos_toggle_health(healthy: bool = False):
    """Fails the liveness probe to trigger Kubernetes pod replacement."""
    _chaos_state["is_healthy"] = healthy
    return {"status": "UPDATED", "is_healthy": healthy}


@app.post("/chaos/unready")
def chaos_toggle_ready(ready: bool = False):
    """Fails the readiness probe to simulate downstream traffic shedding."""
    _chaos_state["is_ready"] = ready
    return {"status": "UPDATED", "is_ready": ready}


@app.post("/chaos/oom")
def chaos_memory_leak(megabytes: int = 150):
    """Allocates memory chunks to simulate an OOMKill or memory spike."""
    try:
        # Allocate bytes in chunks
        chunk = bytearray(megabytes * 1024 * 1024)
        _memory_hog.append(chunk)
        _chaos_state["memory_leak_mb"] += megabytes
        return {
            "status": "ALLOCATED",
            "allocated_mb": megabytes,
            "total_leak_mb": _chaos_state["memory_leak_mb"],
        }
    except MemoryError:
        raise HTTPException(status_code=500, detail="Out of Memory triggered!")


@app.post("/chaos/cpu")
def chaos_cpu_stress(duration_sec: int = 15):
    """Generates a CPU spike to trigger HPA scaling or CPU-throttling alert."""
    def _stress():
        _chaos_state["cpu_stress_active"] = True
        end_time = time.time() + duration_sec
        while time.time() < end_time:
            _ = [x**2 for x in range(10000)]
            time.sleep(0.001)
        _chaos_state["cpu_stress_active"] = False

    threading.Thread(target=_stress).start()
    return {"status": "TRIGGERED", "duration_sec": duration_sec}


@app.post("/chaos/latency")
def chaos_latency(seconds: float = 2.0):
    """Injects artificial latency to trigger SLO/Latency alert."""
    _chaos_state["artificial_latency_sec"] = seconds
    return {"status": "APPLIED", "artificial_latency_sec": seconds}


@app.post("/chaos/errors")
def chaos_http_errors(enable: bool = True):
    """Causes application to return 500 errors to simulate application bug."""
    _chaos_state["simulated_errors"] = enable
    return {"status": "UPDATED", "simulated_errors": enable}


@app.post("/chaos/reset")
def chaos_reset():
    """Resets all injected chaos to pristine state."""
    global _memory_hog
    _memory_hog.clear()
    _chaos_state["is_healthy"] = True
    _chaos_state["is_ready"] = True
    _chaos_state["cpu_stress_active"] = False
    _chaos_state["artificial_latency_sec"] = 0.0
    _chaos_state["memory_leak_mb"] = 0
    _chaos_state["simulated_errors"] = False
    return {"status": "RESET_COMPLETE", "chaos_state": _chaos_state}


# --- Static Files / Mission Control Dashboard UI ---
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return "<h1>AEGIS Mission Control Dashboard loading...</h1>"
