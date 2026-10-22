# AEGIS Chaos Injection CLI
param (
    [string]$Type = "menu"
)

function Show-Menu {
    Clear-Host
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "  AEGIS // Chaos Engineering & Failure Injection Suite" -ForegroundColor Red
    Write-Host "==========================================================" -ForegroundColor Red
    Write-Host "1. Trigger Memory Leak (OOMKill Pressure)" -ForegroundColor Yellow
    Write-Host "2. Trigger Instant Process Crash (CrashLoopBackOff)" -ForegroundColor Yellow
    Write-Host "3. Trigger CPU Stress Burn (15s Spike)" -ForegroundColor Yellow
    Write-Host "4. Inject Latency SLO Breach (2.5s Delay)" -ForegroundColor Yellow
    Write-Host "5. Inject Cascading HTTP 500 Errors" -ForegroundColor Yellow
    Write-Host "6. Reset All Chaos to Nominal Health" -ForegroundColor Green
    Write-Host "7. Exit"
    Write-Host "==========================================================" -ForegroundColor Red
    $choice = Read-Host "Select failure scenario (1-7)"
    return $choice
}

function Execute-Chaos($endpoint) {
    $url = "http://localhost:8080/chaos/$endpoint"
    Write-Host "Sending POST request to $url..." -ForegroundColor Cyan
    try {
        $response = Invoke-RestMethod -Uri $url -Method Post
        Write-Host "Response received:" -ForegroundColor Green
        $response | ConvertTo-Json -Depth 3 | Write-Host
    } catch {
        Write-Host "Failed or process terminated as expected: $_" -ForegroundColor Yellow
    }
}

switch ($Type) {
    "oom"     { Execute-Chaos "oom?megabytes=120" }
    "crash"   { Execute-Chaos "crash" }
    "cpu"     { Execute-Chaos "cpu?duration_sec=15" }
    "latency" { Execute-Chaos "latency?seconds=2.5" }
    "errors"  { Execute-Chaos "errors?enable=true" }
    "reset"   { Execute-Chaos "reset" }
    default {
        $userChoice = Show-Menu
        switch ($userChoice) {
            "1" { Execute-Chaos "oom?megabytes=120" }
            "2" { Execute-Chaos "crash" }
            "3" { Execute-Chaos "cpu?duration_sec=15" }
            "4" { Execute-Chaos "latency?seconds=2.5" }
            "5" { Execute-Chaos "errors?enable=true" }
            "6" { Execute-Chaos "reset" }
            "7" { exit 0 }
            default { Write-Host "Invalid option" }
        }
    }
}
