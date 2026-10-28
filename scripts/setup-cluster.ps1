# AEGIS Automated Cluster & Platform Provisioner
$ErrorActionPreference = "Continue"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AEGIS // Autonomous SRE & AIOps Platform Setup" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Check Docker daemon
Write-Host "[1/6] Checking Docker daemon..." -ForegroundColor Yellow
docker info > $null 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[ERROR] Docker Desktop is not running. Please start Docker Desktop first!" -ForegroundColor Red
    exit 1
}
Write-Host "  Docker is healthy." -ForegroundColor Green

# 2. Resolve Kind binary
Write-Host "[2/6] Verifying Kind installation..." -ForegroundColor Yellow
$kindPath = "$PSScriptRoot\kind.exe"
if (Get-Command "kind" -ErrorAction SilentlyContinue) {
    $kindCmd = "kind"
} elseif (Test-Path $kindPath) {
    $kindCmd = $kindPath
} else {
    Write-Host "  Downloading standalone kind.exe binary..." -ForegroundColor Yellow
    curl.exe -L -o $kindPath "https://github.com/kubernetes-sigs/kind/releases/download/v0.22.0/kind-windows-amd64"
    $kindCmd = $kindPath
}
Write-Host "  Using Kind: $kindCmd" -ForegroundColor Green

# 3. Create or reuse Kind cluster
Write-Host "[3/6] Setting up lightweight Kind cluster (aegis-cluster)..." -ForegroundColor Yellow
$clusters = & $kindCmd get clusters 2>&1
if ($clusters -notcontains "aegis-cluster") {
    & $kindCmd create cluster --name aegis-cluster --config "$PSScriptRoot\kind-config.yaml"
} else {
    Write-Host "  Cluster 'aegis-cluster' already exists. Reusing existing cluster." -ForegroundColor Green
}

# 4. Build Docker images (Fast lightweight build)
Write-Host "[4/6] Building AEGIS microservices..." -ForegroundColor Yellow
docker build -t aegis-core:latest "D:\aegis-platform\app"
docker build -t aegis-controller:latest "D:\aegis-platform\controller"

# 5. Load images into Kind
Write-Host "[5/6] Loading images into Kind cluster..." -ForegroundColor Yellow
& $kindCmd load docker-image aegis-core:latest --name aegis-cluster
& $kindCmd load docker-image aegis-controller:latest --name aegis-cluster

# 6. Apply manifests
Write-Host "[6/6] Applying Kubernetes manifests & RBAC policies..." -ForegroundColor Yellow
kubectl apply -f "D:\aegis-platform\k8s\base\namespace.yaml"
kubectl apply -f "D:\aegis-platform\k8s\base\rbac.yaml"
kubectl apply -f "D:\aegis-platform\k8s\base\app-deployment.yaml"
kubectl apply -f "D:\aegis-platform\k8s\base\app-service.yaml"
kubectl apply -f "D:\aegis-platform\k8s\base\controller-deployment.yaml"

Write-Host "Waiting for deployments to roll out..." -ForegroundColor Yellow
kubectl rollout status deployment/aegis-core -n production-apps --timeout=90s
kubectl rollout status deployment/aegis-controller -n aegis-system --timeout=90s

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Green
Write-Host "  AEGIS Platform is ONLINE & RUNNING!" -ForegroundColor Green
Write-Host "  Mission Control UI: http://localhost:8080" -ForegroundColor Cyan
Write-Host "  Telemetry Metrics:  http://localhost:8080/metrics" -ForegroundColor Cyan
Write-Host "  Health Probe:       http://localhost:8080/healthz" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Green
