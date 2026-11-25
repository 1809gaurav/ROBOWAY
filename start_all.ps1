param(
    [switch]$NoBrowser,
    [switch]$Demo,
    [switch]$Tunnel
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Logs = Join-Path $Root "logs"
$BackendLog = Join-Path $Logs "backend.log"
$FrontendLog = Join-Path $Logs "frontend.log"
$PidFile = Join-Path $Logs "pids.json"
$Started = @{}

function Write-Step([string]$Message) { Write-Host "[ROBOWAY] $Message" -ForegroundColor Cyan }
function Write-Ok([string]$Message) { Write-Host "[  OK  ] $Message" -ForegroundColor Green }
function Write-Warn([string]$Message) { Write-Host "[ INFO ] $Message" -ForegroundColor Yellow }
function Write-Fail([string]$Message) { Write-Host "[ FAIL ] $Message" -ForegroundColor Red }
function Save-Pids {
    $snapshot = [ordered]@{ backend = $Started.backend; frontend = $Started.frontend; tunnel = $Started.tunnel; demo = $Started.demo }
    $snapshot | ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8
}
function Stop-Tree([int]$ProcessId) {
    if ($ProcessId -le 0) { return }
    if ($env:OS -eq "Windows_NT") {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
        foreach ($child in $children) { Stop-Tree ([int]$child.ProcessId) }
    }
    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process) { Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue }
}
function Stop-Started {
    if ($Started.demo) {
        try { Invoke-RestMethod -Method Post -Uri "http://localhost:8000/api/sim/pause" -TimeoutSec 2 | Out-Null } catch { }
    }
    foreach ($key in @("demo", "tunnel", "frontend", "backend")) {
        if ($Started[$key]) { Stop-Tree ([int]$Started[$key]) }
    }
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }
}
function Read-Tail([string]$Path) {
    if (Test-Path $Path) {
        Write-Host "--- Last 20 lines: $Path ---" -ForegroundColor DarkYellow
        Get-Content $Path -Tail 20
    } else {
        Write-Host "Log not created: $Path" -ForegroundColor DarkYellow
    }
}
function Wait-Url([string]$Url, [string]$Name, [string]$LogPath) {
    $deadline = (Get-Date).AddSeconds(30)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 2 -UseBasicParsing
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                Write-Ok "$Name is ready at $Url"
                return
            }
        } catch { Start-Sleep -Milliseconds 500 }
    }
    Read-Tail $LogPath
    throw "$Name did not start within 30 seconds. Inspect $LogPath and fix the first reported startup error."
}
function Invoke-Api([string]$Method, [string]$Url, $Body = $null) {
    if ($null -eq $Body) { return Invoke-RestMethod -Method $Method -Uri $Url -TimeoutSec 8 }
    return Invoke-RestMethod -Method $Method -Uri $Url -ContentType "application/json" -Body ($Body | ConvertTo-Json -Compress) -TimeoutSec 8
}

try {
    New-Item -ItemType Directory -Force -Path $Logs | Out-Null
    if (Test-Path $PidFile) {
        $old = Get-Content $PidFile -Raw | ConvertFrom-Json
        $live = @($old.backend, $old.frontend, $old.tunnel, $old.demo) | Where-Object { $_ -and (Get-Process -Id ([int]$_) -ErrorAction SilentlyContinue) }
        if ($live.Count -gt 0) {
            throw "ROBOWAY process(es) already recorded as running ($($live -join ', ')). Stop them first with: .\stop_all.ps1"
        }
        Remove-Item $PidFile -Force
    }

    Write-Step "Checking Python and Node.js prerequisites"
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCommand) { throw "Python was not found. Install Python 3.11 or newer from https://www.python.org/downloads/ and enable 'Add python.exe to PATH'." }
    $pythonVersionText = (& python --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $pythonVersionText -notmatch "Python\s+(\d+)\.(\d+)") { throw "Could not read the Python version. Fix the Python installation and ensure 'python' works in PowerShell." }
    if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 11)) { throw "Found $pythonVersionText; install Python 3.11 or newer, then rerun .\start_all.ps1." }
    Write-Ok $pythonVersionText

    $nodeCommand = Get-Command node -ErrorAction SilentlyContinue
    if (-not $nodeCommand) { throw "Node.js was not found. Install Node.js 18 or newer from https://nodejs.org/ and add node.exe to PATH." }
    $nodeVersion = (& node --version 2>&1 | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch "^v?(\d+)") { throw "Could not read the Node.js version. Fix the Node.js installation and ensure 'node' works in PowerShell." }
    if ([int]$Matches[1] -lt 18) { throw "Found Node.js $nodeVersion; install Node.js 18 or newer, then rerun .\start_all.ps1." }
    Write-Ok "Node.js $nodeVersion"

    $VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
    if ($env:OS -ne "Windows_NT") { $VenvPython = Join-Path $Root ".venv/bin/python" }
    if (-not (Test-Path $VenvPython)) {
        Write-Step "Creating root .venv"
        & python -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed. Repair Python's venv support, then rerun .\start_all.ps1." }
    }
    Write-Step "Installing backend dependencies"
    & $VenvPython -m pip install -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Backend dependency installation failed. Check internet/package-index access, then rerun .\start_all.ps1." }

    $Frontend = Join-Path $Root "frontend"
    if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
        Write-Step "Installing frontend dependencies"
        Push-Location $Frontend
        try { npm install; if ($LASTEXITCODE -ne 0) { throw "npm install failed. Check Node.js/npm and network access, then rerun .\start_all.ps1." } }
        finally { Pop-Location }
    } else { Write-Ok "frontend/node_modules already exists; skipping npm install" }

    Write-Step "Detecting LAN IPv4 address"
    $LanIp = $null
    if ($env:OS -eq "Windows_NT" -and (Get-Command Get-NetIPConfiguration -ErrorAction SilentlyContinue)) {
        $configs = Get-NetIPConfiguration | Where-Object { $_.NetAdapter.Status -eq "Up" }
        $candidates = foreach ($config in $configs) {
            $alias = [string]$config.InterfaceAlias
            if ($alias -match "(?i)virtual|wsl|vpn|tap|loopback|hyper-v|vmware|virtualbox|docker|tailscale|wireguard|vethernet") { continue }
            foreach ($address in $config.IPv4Address) {
                $ip = [string]$address.IPAddress
                if ($ip -and $ip -notmatch "^(169\.254\.|127\.)") {
                    [pscustomobject]@{ IP = $ip; Gateway = [bool]$config.IPv4DefaultGateway }
                }
            }
        }
        $LanIp = ($candidates | Sort-Object @{Expression = "Gateway"; Descending = $true} | Select-Object -First 1).IP
    }
    if (-not $LanIp) {
        $interfaces = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()
        $networkCandidates = foreach ($adapter in $interfaces) {
            if ($adapter.OperationalStatus.ToString() -ne "Up" -or $adapter.Name -match "(?i)virtual|wsl|vpn|tap|loopback|hyper-v|vmware|virtualbox|docker|tailscale|wireguard|vethernet") { continue }
            $properties = $adapter.GetIPProperties()
            $hasGateway = @($properties.GatewayAddresses | Where-Object { $_.Address.AddressFamily.ToString() -eq "InterNetwork" -and $_.Address.ToString() -ne "0.0.0.0" }).Count -gt 0
            foreach ($unicast in $properties.UnicastAddresses) {
                if ($unicast.Address.AddressFamily.ToString() -ne "InterNetwork") { continue }
                $ip = $unicast.Address.ToString()
                if ($ip -notmatch "^(169\.254\.|127\.)") {
                    [pscustomobject]@{ IP = $ip; Gateway = $hasGateway }
                }
            }
        }
        $LanIp = ($networkCandidates | Sort-Object @{Expression = "Gateway"; Descending = $true} | Select-Object -First 1).IP
    }
    if (-not $LanIp) {
        Write-Warn "No eligible LAN IPv4 address found; using localhost URLs. Check the active network adapter and default gateway."
        $LanIp = "localhost"
    } else { Write-Ok "LAN IPv4: $LanIp" }

    if ($env:OS -eq "Windows_NT") {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
        $principal = New-Object Security.Principal.WindowsPrincipal($identity)
        $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        if ($isAdmin) {
            foreach ($port in @(8000, 5173)) {
                $ruleName = "ROBOWAY TCP $port"
                if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
                    New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port | Out-Null
                }
            }
            Write-Ok "Windows Firewall inbound rules are ready for TCP 8000 and 5173"
        } else {
            Write-Warn "Not running as Administrator; continuing without firewall changes."
            Write-Host 'Run these two commands in an elevated PowerShell shell to allow phone access:' -ForegroundColor Yellow
            Write-Host 'New-NetFirewallRule -DisplayName "ROBOWAY TCP 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000'
            Write-Host 'New-NetFirewallRule -DisplayName "ROBOWAY TCP 5173" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 5173'
        }
    }

    Write-Step "Starting backend; output: logs/backend.log"
    $backend = Start-Process -FilePath $VenvPython -ArgumentList @("-u", "run_server.py", "--host", "0.0.0.0", "--port", "8000") -WorkingDirectory $Root -RedirectStandardOutput $BackendLog -RedirectStandardError (Join-Path $Logs "backend-error.log") -PassThru
    $Started.backend = $backend.Id
    Save-Pids
    $ApiBase = "http://${LanIp}:8000"

    Write-Step "Starting frontend; output: logs/frontend.log"
    $frontendLog = $FrontendLog.Replace('"', '""')
    if ($env:OS -eq "Windows_NT") {
        $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
        $command = 'set "VITE_API_BASE={0}"&& cd /d "{1}"&& call "{2}" run dev -- --host 0.0.0.0 >> "{3}" 2>&1' -f $ApiBase, $Frontend, $npm, $frontendLog
        $front = Start-Process -FilePath $env:ComSpec -ArgumentList @("/c", $command) -WorkingDirectory $Root -PassThru
    } else {
        $oldApiBase = $env:VITE_API_BASE
        $env:VITE_API_BASE = $ApiBase
        try { $front = Start-Process -FilePath "npm" -ArgumentList @("run", "dev", "--", "--host", "0.0.0.0") -WorkingDirectory $Frontend -RedirectStandardOutput $FrontendLog -RedirectStandardError (Join-Path $Logs "frontend-error.log") -PassThru }
        finally { $env:VITE_API_BASE = $oldApiBase }
    }
    $Started.frontend = $front.Id
    Save-Pids

    Wait-Url "http://localhost:8000/health" "Backend" $BackendLog
    Wait-Url "http://localhost:5173/" "Frontend" $FrontendLog
    $null = Invoke-Api "POST" "http://localhost:8000/api/scenarios/narrow_passage/load"
    if ($Demo) {
        $null = Invoke-Api "POST" "http://localhost:8000/api/sim/start"
        Write-Ok "Loaded narrow_passage and started the demo simulation"
    } else {
        $null = Invoke-Api "POST" "http://localhost:8000/api/sim/pause"
        Write-Ok "Loaded narrow_passage and left it paused"
    }

    $dashboard = "http://${LanIp}:5173"
    $phone = "http://${LanIp}:5173/monitor?api=$([uri]::EscapeDataString($ApiBase))"
    $ml = Invoke-Api "GET" "http://localhost:8000/api/ml/status"
    if ($ml.enabled) { $mlText = "ML: enabled, model $($ml.model)" } else { $mlText = "ML: disabled, no model loaded" }
    Write-Host ""
    Write-Host "+------------------------------------------------------------+" -ForegroundColor Green
    Write-Host "| ROBOWAY READY                                              |" -ForegroundColor Green
    Write-Host ("| Dashboard:     {0}" -f $dashboard)
    Write-Host ("| Phone monitor: {0}" -f $phone)
    Write-Host "| API state:     http://${LanIp}:8000/api/state"
    Write-Host "| $mlText"
    Write-Host "| Logs:          $Logs"
    Write-Host "+------------------------------------------------------------+" -ForegroundColor Green
    Write-Host "Phone monitor QR:" -ForegroundColor Cyan
    & $VenvPython (Join-Path $Root "scripts\print_qr.py") $phone
    if ($LASTEXITCODE -ne 0) { Write-Warn "QR output was unavailable. Install dependencies with: .\.venv\Scripts\python.exe -m pip install -r requirements.txt" }

    if ($Tunnel) {
        $cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
        if ($cloudflared) {
            $tunnelLog = Join-Path $Logs "tunnel.log"
            $tunnel = Start-Process -FilePath $cloudflared.Source -ArgumentList @("tunnel", "--url", "http://localhost:8000") -RedirectStandardOutput $tunnelLog -RedirectStandardError (Join-Path $Logs "tunnel-error.log") -PassThru
            $Started.tunnel = $tunnel.Id
            Save-Pids
            $deadline = (Get-Date).AddSeconds(30)
            $tunnelUrl = $null
            while ((Get-Date) -lt $deadline -and -not $tunnelUrl) {
                if (Test-Path $tunnelLog) {
                    $match = Select-String -Path $tunnelLog -Pattern "https://[a-zA-Z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
                    if ($match) { $tunnelUrl = $match.Matches[0].Value }
                }
                if (-not $tunnelUrl) { Start-Sleep -Milliseconds 500 }
            }
            if ($tunnelUrl) {
                Write-Host "Cloudflare tunnel: $tunnelUrl" -ForegroundColor Green
                Write-Host "Phone monitor (tunnel API): http://${LanIp}:5173/monitor?api=$([uri]::EscapeDataString($tunnelUrl))" -ForegroundColor Green
            } else { Write-Warn "cloudflared started but no HTTPS URL appeared within 30 seconds. See logs/tunnel.log." }
        } else {
            Write-Warn "cloudflared is not installed. Install it from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/, then rerun .\start_all.ps1 -Tunnel."
        }
    }

    if ($Demo) {
        $demo = Start-Process -FilePath $VenvPython -ArgumentList @("-u", "scripts/demo_autoplay.py", "--api", "http://localhost:8000", "--loop") -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Logs "demo.log") -RedirectStandardError (Join-Path $Logs "demo-error.log") -PassThru
        $Started.demo = $demo.Id
        Save-Pids
        Write-Ok "Hands-free demo player started; output: logs/demo.log"
    }
    if (-not $NoBrowser) { Start-Process $dashboard }
    Write-Host "Press Ctrl+C to stop ROBOWAY, or run .\stop_all.ps1 in another PowerShell window." -ForegroundColor Cyan
    if ($Demo) {
        while ($true) { Start-Sleep -Seconds 2 }
    } else {
        while ($true) { Start-Sleep -Seconds 5 }
    }
} catch {
    Write-Fail $_.Exception.Message
    Write-Host "Fix the indicated prerequisite/startup issue, then rerun: .\start_all.ps1" -ForegroundColor Red
    Stop-Started
    exit 1
}
finally {
    Stop-Started
}
