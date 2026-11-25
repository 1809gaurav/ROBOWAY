$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$Logs = Join-Path $Root "logs"
$HostExe = (Get-Process -Id $PID).Path
$Launcher = $null
$Results = [System.Collections.Generic.List[object]]::new()
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if ($env:OS -ne "Windows_NT") { $VenvPython = Join-Path $Root ".venv/bin/python" }

function Add-Result([string]$Name, [string]$Status, [string]$Details = "") {
    $script:Results.Add([pscustomobject]@{ Name = $Name; Status = $Status; Details = $Details }) | Out-Null
    $color = if ($Status -eq "PASS") { "Green" } elseif ($Status -eq "SKIP") { "Yellow" } else { "Red" }
    Write-Host "[$Status] $Name $Details" -ForegroundColor $color
}
function Run-External([string]$Name, [scriptblock]$Command) {
    Write-Host "`n=== $Name ===" -ForegroundColor Cyan
    $output = @(& $Command 2>&1)
    $code = $LASTEXITCODE
    foreach ($line in $output) { Write-Host $line }
    if ($code -eq 0 -and -not (($output | Out-String) -match "(?m)^SKIP:")) {
        Add-Result $Name "PASS"
    } elseif ($code -eq 0) {
        Add-Result $Name "SKIP" (($output | Where-Object { "$_" -match "^SKIP:" } | Select-Object -First 1) -join "")
    } else {
        Add-Result $Name "FAIL" "Exit code $code"
    }
}
function Wait-Health([int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -eq 200) { return $true }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    return $false
}

try {
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null
    $launcherArgs = @("-NoProfile", "-File", (Join-Path $Root "start_all.ps1"), "-NoBrowser")
    if ($env:OS -eq "Windows_NT") { $launcherArgs = @("-NoProfile", "-ExecutionPolicy", "Bypass") + $launcherArgs }
    $Launcher = Start-Process -FilePath $HostExe -ArgumentList $launcherArgs -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Logs "verify-launcher.log") -RedirectStandardError (Join-Path $Logs "verify-launcher-error.log") -PassThru
    if (-not (Wait-Health 150)) {
        Add-Result "One-command startup" "FAIL" "Backend did not become healthy; inspect logs/verify-launcher.log and logs/backend.log"
    } else {
        Add-Result "One-command startup" "PASS"
        & $VenvPython -m pip install -r (Join-Path $Root "requirements-dev.txt")
        if ($LASTEXITCODE -ne 0) {
            Add-Result "Install verification dependencies" "FAIL" "Fix pip/package access for requirements-dev.txt"
        } else {
            Add-Result "Install verification dependencies" "PASS"
            Run-External "pytest -q" { Set-Location $Root; & $VenvPython -m pytest -q }
            Run-External "npm run build" { Set-Location (Join-Path $Root "frontend"); npm run build }
            Run-External "npm test" { Set-Location (Join-Path $Root "frontend"); npm test }
            Run-External "e2e_smoke.py" { Set-Location $Root; & $VenvPython "scripts/e2e_smoke.py" --api "http://127.0.0.1:8000" }
            Run-External "e2e_browser.py" { Set-Location $Root; & $VenvPython "scripts/e2e_browser.py" }
        }
    }
} catch {
    Add-Result "verify_all.ps1 execution" "FAIL" $_.Exception.Message
} finally {
    & (Join-Path $Root "stop_all.ps1")
    if ($Launcher -and (Get-Process -Id $Launcher.Id -ErrorAction SilentlyContinue)) {
        Stop-Process -Id $Launcher.Id -Force -ErrorAction SilentlyContinue
    }
}

$dashboard = "http://localhost:5173"
$phone = "http://localhost:5173/monitor?api=http%3A%2F%2Flocalhost%3A8000"
$apiState = "http://localhost:8000/api/state"
$launcherLog = Join-Path $Logs "verify-launcher.log"
if (Test-Path $launcherLog) {
    $dashboardMatch = Select-String -Path $launcherLog -Pattern "Dashboard:\s+(https?://\S+)" | Select-Object -Last 1
    $phoneMatch = Select-String -Path $launcherLog -Pattern "Phone monitor:\s+(https?://\S+)" | Select-Object -Last 1
    if ($dashboardMatch) { $dashboard = $dashboardMatch.Matches[0].Groups[1].Value }
    if ($phoneMatch) { $phone = $phoneMatch.Matches[0].Groups[1].Value }
}
$ready = -not ($Results | Where-Object { $_.Status -eq "FAIL" })
$mlStatus = "ML: disabled, no model loaded"
try {
    if (Test-Path (Join-Path $Root "logs\backend.log")) {
        # Launcher prints the authoritative status after loading the real model adapter.
        $mlLine = Select-String -Path $launcherLog -Pattern "ML:\s+.*" | Select-Object -Last 1
        if ($mlLine) { $mlStatus = $mlLine.Line.Trim("| ") }
    }
} catch { }

Write-Host "`n================ FINAL REPORT ================" -ForegroundColor Cyan
Write-Host ("STATUS: {0}" -f $(if ($ready) { "READY" } else { "NOT READY" })) -ForegroundColor $(if ($ready) { "Green" } else { "Red" })
Write-Host "Dashboard:     $dashboard"
Write-Host "Phone monitor: $phone"
Write-Host "API state:     $apiState"
Write-Host $mlStatus
Write-Host "Known limitations: no ML model is loaded; the engine does not provide battery data."
Write-Host "`nCHECK                 RESULT  DETAILS"
Write-Host "---------------------  ------  -------"
foreach ($result in $Results) { Write-Host ("{0,-21}  {1,-6}  {2}" -f $result.Name, $result.Status, $result.Details) }
if (-not $ready) { exit 1 }
