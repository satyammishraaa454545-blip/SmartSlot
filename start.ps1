<#
.SYNOPSIS
  Starts SmartSlot: the API on http://localhost:8000 and (if present) the web UI on http://localhost:5173.

.DESCRIPTION
  Each server opens in its own PowerShell window. With no switches both are started.
  The API runs with SMARTSLOT_DEV=1, which enables POST /api/dev/reset (wipe + optional sample load).

.PARAMETER Backend
  Start only the API (uvicorn, port 8000).

.PARAMETER Frontend
  Start only the web UI (Vite dev server, port 5173; needs frontend/package.json).

.PARAMETER LoadSample
  After the API is up, wipe the database and load the feasible demo dataset (dev reset).

.PARAMETER Reload
  Restart the API automatically when backend code changes (for development).

.EXAMPLE
  .\start.ps1                 # both servers
  .\start.ps1 -Backend        # API only
  .\start.ps1 -Backend -LoadSample
#>
[CmdletBinding()]
param(
    [switch]$Backend,
    [switch]$Frontend,
    [switch]$LoadSample,
    [switch]$Reload
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$backendDir = Join-Path $root 'backend'
$frontendDir = Join-Path $root 'frontend'
$venvPython = Join-Path $backendDir '.venv\Scripts\python.exe'

if (-not $Backend -and -not $Frontend) { $Backend = $true; $Frontend = $true }

function Test-Port([int]$Port) {
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.Connect('127.0.0.1', $Port)
        $client.Close()
        return $true
    } catch { return $false }
}

if ($Backend) {
    if (-not (Test-Path $venvPython)) {
        Write-Host 'Creating the Python environment (first run only)...' -ForegroundColor Cyan
        & python -m venv (Join-Path $backendDir '.venv')
        & $venvPython -m pip install --quiet -r (Join-Path $backendDir 'requirements.txt')
    }
    if (Test-Port 8000) {
        Write-Host 'Port 8000 is already in use - assuming the API is already running.' -ForegroundColor Yellow
    } else {
        $uvicorn = "& '$venvPython' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
        if ($Reload) { $uvicorn += ' --reload --reload-dir app' }
        $command = "`$env:SMARTSLOT_DEV = '1'; `$host.UI.RawUI.WindowTitle = 'SmartSlot API :8000'; $uvicorn"
        Start-Process powershell -WorkingDirectory $backendDir -ArgumentList '-NoExit', '-NoProfile', '-Command', $command | Out-Null
        Write-Host 'Starting the API on http://localhost:8000  (docs: http://localhost:8000/docs)' -ForegroundColor Green
    }

    # Wait until it answers, so "-LoadSample" and the first browser visit work.
    $up = $false
    for ($i = 0; $i -lt 40 -and -not $up; $i++) {
        try {
            $health = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/health' -TimeoutSec 2
            $up = ($health.status -eq 'ok')
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if ($up) {
        Write-Host 'API is healthy.' -ForegroundColor Green
        if ($LoadSample) {
            $r = Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/api/dev/reset?sample=feasible'
            Write-Host "Database reset; loaded dataset #$($r.dataset.id): $($r.dataset.name)" -ForegroundColor Green
        }
    } else {
        Write-Host 'The API did not answer within 20 seconds - check its window for errors.' -ForegroundColor Red
    }
}

if ($Frontend) {
    if (-not (Test-Path (Join-Path $frontendDir 'package.json'))) {
        Write-Host 'frontend/package.json not found - skipping the web UI.' -ForegroundColor Yellow
    } elseif (Test-Port 5173) {
        Write-Host 'Port 5173 is already in use - assuming the web UI is already running.' -ForegroundColor Yellow
    } else {
        if (-not (Test-Path (Join-Path $frontendDir 'node_modules'))) {
            Write-Host 'Installing web UI packages (first run only)...' -ForegroundColor Cyan
            Push-Location $frontendDir
            try { npm install } finally { Pop-Location }
        }
        $command = "`$host.UI.RawUI.WindowTitle = 'SmartSlot UI :5173'; npm run dev -- --port 5173"
        Start-Process powershell -WorkingDirectory $frontendDir -ArgumentList '-NoExit', '-NoProfile', '-Command', $command | Out-Null
        Write-Host 'Starting the web UI on http://localhost:5173' -ForegroundColor Green
    }
}
