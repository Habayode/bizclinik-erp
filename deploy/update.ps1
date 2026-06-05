<#
 .SYNOPSIS
  Pull the latest code from GitHub and restart the BizClinik ERP service.

 .DESCRIPTION
  Safe, hang-free redeploy:
    1. Force-stop the Streamlit service (kills python so the file copy + DB
       migration aren't blocked by an open handle).
    2. Download the latest main.zip, overwrite code (preserving data/ + venv/).
    3. pip install -r requirements.txt (in case deps changed).
    4. python -m bizclinik_erp init (idempotent migration -- creates any new
       tables without touching existing rows).
    5. Start the service and poll health.

  Run elevated. Does NOT touch cloudflared (the tunnel keeps running).

 .EXAMPLE
   .\deploy\update.ps1
#>
[CmdletBinding()]
param(
    [string]$AppRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [int]$Port = 8501
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function Write-Step($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }

$venvPy = Join-Path $AppRoot "venv\Scripts\python.exe"
$venvPip = Join-Path $AppRoot "venv\Scripts\pip.exe"

Write-Step "Stopping BizClinikERP (force)"
# Don't rely on Stop-Service alone -- kill python so handles release immediately.
Get-Process python, pythonw -ErrorAction SilentlyContinue | Stop-Process -Force
$svc = Get-Service BizClinikERP -ErrorAction SilentlyContinue
if ($svc) {
    Stop-Service BizClinikERP -Force -ErrorAction SilentlyContinue
    # Give SCM a moment; if it's wedged in STOP_PENDING the kill above clears it.
    Start-Sleep -Seconds 3
}

Write-Step "Downloading latest code"
$zip = Join-Path $env:TEMP "bizclinik-erp-update.zip"
$extract = Join-Path $env:TEMP "bizclinik-erp-update"
if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
Invoke-WebRequest -Uri "https://github.com/Habayode/bizclinik-erp/archive/refs/heads/main.zip" `
    -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath $extract -Force
$srcRoot = Join-Path $extract "bizclinik-erp-main"

Write-Step "Overwriting code (preserving data/ and venv/)"
# Copy everything except data/ and venv/.
Get-ChildItem -Path $srcRoot | Where-Object {
    $_.Name -ne "data" -and $_.Name -ne "venv"
} | ForEach-Object {
    Copy-Item -Path $_.FullName -Destination $AppRoot -Recurse -Force
}

Write-Step "Installing requirements"
& $venvPip install -r (Join-Path $AppRoot "requirements.txt") | Out-Null

Write-Step "Running idempotent DB migration"
Push-Location $AppRoot
& $venvPy -m bizclinik_erp init
Pop-Location

Write-Step "Starting BizClinikERP"
Start-Service BizClinikERP

Write-Step "Waiting for health"
$ok = $false
for ($i = 1; $i -le 30; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest "http://localhost:$Port/_stcore/health" `
            -UseBasicParsing -TimeoutSec 3
        if ($r.Content -eq "ok") { $ok = $true; break }
    } catch { }
}

Write-Host ""
if ($ok) {
    Write-Host "Update complete. Local health: ok" -ForegroundColor Green
    try {
        $pub = Invoke-WebRequest "https://erp.hagai.online/_stcore/health" `
            -UseBasicParsing -TimeoutSec 12
        Write-Host "Public health: $($pub.Content)" -ForegroundColor Green
    } catch {
        Write-Host "Public not yet responding (tunnel may need a few seconds)." -ForegroundColor Yellow
    }
} else {
    Write-Host "Service did not become healthy within 60s." -ForegroundColor Red
    Write-Host "Check: Get-Content $AppRoot\logs\streamlit.log -Tail 40"
}

Remove-Item -Force $zip -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force $extract -ErrorAction SilentlyContinue
