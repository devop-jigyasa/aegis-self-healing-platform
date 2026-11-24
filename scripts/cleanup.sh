#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo "  AEGIS // Local Resource Teardown"
echo "=========================================================="

echo "Deleting Kind cluster 'aegis-cluster'..."
kind delete cluster --name aegis-cluster || true

echo "Removing local build images..."
docker rmi aegis-core:latest aegis-controller:latest -f 2>/dev/null || true

echo "Cleanup completed successfully! All local resources freed."
