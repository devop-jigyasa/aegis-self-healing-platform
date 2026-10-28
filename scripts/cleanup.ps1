# AEGIS Cluster Teardown & Resource Cleanup
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AEGIS // Local Resource Teardown" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

Write-Host "Deleting Kind cluster 'aegis-cluster'..." -ForegroundColor Yellow
kind delete cluster --name aegis-cluster

Write-Host "Removing local build images..." -ForegroundColor Yellow
docker rmi aegis-core:latest aegis-controller:latest -f > $null 2>&1

Write-Host "Cleanup completed successfully! All local resources freed." -ForegroundColor Green
