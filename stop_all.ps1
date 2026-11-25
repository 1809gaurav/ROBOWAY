$ErrorActionPreference = "Continue"
$Root = $PSScriptRoot
$PidFile = Join-Path $Root "logs\pids.json"

function Stop-Tree([int]$ProcessId) {
    if ($ProcessId -le 0) { return }
    if ($env:OS -eq "Windows_NT") {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
        foreach ($child in $children) { Stop-Tree ([int]$child.ProcessId) }
    }
    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
        Write-Host "Stopped PID $ProcessId" -ForegroundColor Yellow
    }
}

if (-not (Test-Path $PidFile)) {
    Write-Host "No logs/pids.json found; no ROBOWAY processes are recorded." -ForegroundColor Yellow
    exit 0
}
$pids = Get-Content $PidFile -Raw | ConvertFrom-Json
if ($pids.demo) {
    try { Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/sim/pause" -TimeoutSec 2 | Out-Null }
    catch { Write-Host "Could not pause the simulation before stopping processes: $($_.Exception.Message)" -ForegroundColor Yellow }
}
foreach ($key in @("demo", "tunnel", "frontend", "backend")) {
    $value = $pids.$key
    if ($value) { Stop-Tree ([int]$value) }
}
Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
Write-Host "ROBOWAY processes stopped." -ForegroundColor Green
