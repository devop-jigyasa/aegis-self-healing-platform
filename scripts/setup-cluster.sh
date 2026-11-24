#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  AEGIS // Autonomous SRE & AIOps Platform Setup"
echo "=========================================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# 1. Check Docker daemon
echo "[1/6] Checking Docker daemon..."
if ! docker info > /dev/null 2>&1; then
    echo "[ERROR] Docker is not running. Please start Docker first!" >&2
    exit 1
fi
echo "  Docker is healthy."

# 2. Verify Kind
echo "[2/6] Verifying Kind installation..."
if ! command -v kind > /dev/null 2>&1; then
    echo "[ERROR] kind is not installed. Please install Kind: https://kind.sigs.k8s.io/docs/user/quick-start/" >&2
    exit 1
fi
echo "  Using Kind: $(command -v kind)"

# 3. Create or reuse Kind cluster
echo "[3/6] Setting up lightweight Kind cluster (aegis-cluster)..."
if ! kind get clusters 2>/dev/null | grep -q "^aegis-cluster$"; then
    kind create cluster --name aegis-cluster --config "${SCRIPT_DIR}/kind-config.yaml"
else
    echo "  Cluster 'aegis-cluster' already exists. Reusing existing cluster."
fi

# 4. Build Docker images
echo "[4/6] Building AEGIS microservices..."
docker build -t aegis-core:1.0.0 -t aegis-core:latest "${REPO_ROOT}/app"
docker build -t aegis-controller:1.0.0 -t aegis-controller:latest "${REPO_ROOT}/controller"

# 5. Load images into Kind
echo "[5/6] Loading images into Kind cluster..."
kind load docker-image aegis-core:1.0.0 --name aegis-cluster
kind load docker-image aegis-controller:1.0.0 --name aegis-cluster

# 6. Apply manifests & monitoring stack
echo "[6/6] Applying Kubernetes manifests, RBAC & Monitoring Stack..."
kubectl apply -f "${REPO_ROOT}/k8s/base/namespace.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/base/rbac.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/base/app-deployment.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/base/app-service.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/base/controller-deployment.yaml"
kubectl apply -f "${REPO_ROOT}/k8s/monitoring/monitoring-stack.yaml"

echo "Waiting for deployments to roll out..."
kubectl rollout status deployment/aegis-core -n production-apps --timeout=90s
kubectl rollout status deployment/aegis-controller -n aegis-system --timeout=90s

echo ""
echo "=========================================================="
echo "  AEGIS Platform is ONLINE & RUNNING!"
echo "  Mission Control UI: http://localhost:8080"
echo "  Telemetry Metrics:  http://localhost:8080/metrics"
echo "  Health Probe:       http://localhost:8080/healthz"
echo "  Controller API:     http://localhost:5000/api/circuit-breaker"
echo "=========================================================="
