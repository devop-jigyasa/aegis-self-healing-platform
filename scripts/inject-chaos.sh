#!/usr/bin/env bash
set -euo pipefail

SCENARIO="${1:-menu}"
BASE_URL="http://localhost:8080/chaos"

execute_chaos() {
    local endpoint="$1"
    echo "Sending POST request to ${BASE_URL}/${endpoint}..."
    curl -s -X POST "${BASE_URL}/${endpoint}" || echo " (Request sent; process may have terminated or timed out)"
    echo ""
}

show_menu() {
    echo "=========================================================="
    echo "  AEGIS // Chaos Engineering & Failure Injection Suite"
    echo "=========================================================="
    echo "1. Trigger Memory Leak (OOMKill Pressure)"
    echo "2. Trigger Instant Process Crash (CrashLoopBackOff)"
    echo "3. Trigger CPU Stress Burn (15s Spike)"
    echo "4. Inject Latency SLO Breach (2.5s Delay)"
    echo "5. Inject Cascading HTTP 500 Errors"
    echo "6. Reset All Chaos to Nominal Health"
    echo "7. Exit"
    echo "=========================================================="
    read -rp "Select failure scenario (1-7): " choice
    case "$choice" in
        1) execute_chaos "oom?megabytes=120" ;;
        2) execute_chaos "crash" ;;
        3) execute_chaos "cpu?duration_sec=15" ;;
        4) execute_chaos "latency?seconds=2.5" ;;
        5) execute_chaos "errors?enable=true" ;;
        6) execute_chaos "reset" ;;
        7) exit 0 ;;
        *) echo "Invalid option" ;;
    esac
}

case "${SCENARIO,,}" in
    oom)       execute_chaos "oom?megabytes=120" ;;
    crash)     execute_chaos "crash" ;;
    crashloop) execute_chaos "crash" ;;
    cpu)       execute_chaos "cpu?duration_sec=15" ;;
    latency)   execute_chaos "latency?seconds=2.5" ;;
    errors)    execute_chaos "errors?enable=true" ;;
    reset)     execute_chaos "reset" ;;
    menu)      show_menu ;;
    *)
        echo "Unknown scenario: $SCENARIO"
        echo "Valid options: oom, crash, crashloop, cpu, latency, errors, reset, menu"
        exit 1
        ;;
esac
