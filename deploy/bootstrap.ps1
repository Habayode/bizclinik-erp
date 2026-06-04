<#
 .SYNOPSIS
  One-shot deploy of BizClinik ERP on a Windows VPS, fronted by a Cloudflare
  named tunnel.

 .DESCRIPTION
  Steps performed:
    1. Detect Python 3.11+ (fail with hint if missing)
    2. Create venv at .\venv and pip-install requirements.txt
    3. Initialise the SQLite DB and seed default chart of accounts
    4. Install cloudflared.exe to C:\Program Files (x86)\cloudflared if absent
    5. Log into Cloudflare (one interactive browser step)
    6. Create the named tunnel `bizclinik-erp` if it doesn't exist
    7. Route DNS for the chosen subdomain to that tunnel
    8. Write the tunnel config.yml + install cloudflared as a Windows service
    9. Install the Streamlit app as a Windows service via Task Scheduler
   10. Start both services and print the public URL

 .PARAMETER Subdomain
   Fully-qualified host that should resolve to the ERP (e.g. erp.hagai.online).

 .PARAMETER Password
   Password the ERP will require at the lock screen. Stored as a SYSTEM
   environment variable so it survives reboots.

 .PARAMETER Port
   Local TCP port the Streamlit server listens on. Default 8501.

 .EXAMPLE
   .\bootstrap.ps1 -Subdomain erp.hagai.online -Password 'uBJMglKjLhcWS4KkNjSe'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Subdomain,
    [Parameter(Mandatory = $true)] [string]$Password,
    [int]$Port = 8501,
    [string]$TunnelName = "bizclinik-erp",
    [string]$AppRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = [Security.Principal.WindowsPrincipal]::new($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    throw "Run this script in an elevated PowerShell (Right-click → Run as administrator)."
}

Write-Host "BizClinik ERP — VPS bootstrap" -ForegroundColor Green
Write-Host "  App root  : $AppRoot"
Write-Host "  Subdomain : $Subdomain"
Write-Host "  Tunnel    : $TunnelName"
Write-Host "  Local port: $Port"


# ---- 1. Python ------------------------------------------------------------

Write-Step "Checking Python"
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    throw "Python not found on PATH. Install Python 3.11+ from https://www.python.org/downloads/windows/ and re-run."
}
$pyv = & $python --version
Write-Host "  Found: $pyv"


# ---- 2. venv + deps -------------------------------------------------------

Write-Step "Creating venv and installing requirements"
$venvPath = Join-Path $AppRoot "venv"
if (-not (Test-Path $venvPath)) {
    & $python -m venv $venvPath
}
$venvPy  = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPip install -r (Join-Path $AppRoot "requirements.txt")


# ---- 3. DB init ------------------------------------------------------------

Write-Step "Initialising SQLite database"
Push-Location $AppRoot
& $venvPy -m bizclinik_erp init
Pop-Location


# ---- 4. cloudflared --------------------------------------------------------

Write-Step "Ensuring cloudflared is installed"
$cfDir = "C:\Program Files (x86)\cloudflared"
$cfExe = Join-Path $cfDir "cloudflared.exe"
if (-not (Test-Path $cfExe)) {
    New-Item -ItemType Directory -Force -Path $cfDir | Out-Null
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Write-Host "  Downloading from $url"
    Invoke-WebRequest -Uri $url -OutFile $cfExe -UseBasicParsing
}
# Make sure it's on PATH for this session.
# Note: avoid "$env:Path" in a double-quoted string — PowerShell 5.1's parser
# misreads the colon. Use straight concatenation.
$env:Path = $cfDir + ";" + $env:Path
& $cfExe --version


# ---- 5. Cloudflare login + tunnel + DNS -----------------------------------

$cfHome = Join-Path $env:USERPROFILE ".cloudflared"
$certPem = Join-Path $cfHome "cert.pem"
if (-not (Test-Path $certPem)) {
    Write-Step "Cloudflare login (one-time)"
    Write-Host "  A browser will open. Sign in and authorise the zone for $Subdomain." -ForegroundColor Yellow
    & $cfExe tunnel login
}

Write-Step "Ensuring tunnel '$TunnelName' exists"
$existing = & $cfExe tunnel list 2>$null | Select-String -SimpleMatch $TunnelName
if (-not $existing) {
    & $cfExe tunnel create $TunnelName
}
$tunnelUuid = (& $cfExe tunnel list --output json | ConvertFrom-Json |
               Where-Object { $_.name -eq $TunnelName }).id
if (-not $tunnelUuid) {
    throw "Could not resolve tunnel UUID for $TunnelName"
}
$credFile = Join-Path $cfHome "$tunnelUuid.json"
Write-Host "  Tunnel UUID: $tunnelUuid"

Write-Step "Routing DNS $Subdomain -> $TunnelName"
& $cfExe tunnel route dns $TunnelName $Subdomain


# ---- 6. tunnel config -----------------------------------------------------

Write-Step "Writing tunnel config.yml"
$cfgPath = Join-Path $cfHome "config.yml"
@"
tunnel: $tunnelUuid
credentials-file: $credFile

ingress:
  - hostname: $Subdomain
    service: http://localhost:$Port
    originRequest:
      noTLSVerify: true
  - service: http_status:404
"@ | Out-File -FilePath $cfgPath -Encoding utf8 -Force


# ---- 7. cloudflared as Windows service ------------------------------------

Write-Step "Installing cloudflared as a Windows service"
$svc = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "  cloudflared service already exists — reinstalling to pick up new config"
    & $cfExe service uninstall | Out-Null
}
& $cfExe --config $cfgPath service install


# ---- 8. Streamlit as Windows service (Task Scheduler) ---------------------

Write-Step "Setting up the ERP environment variable (SYSTEM scope)"
[Environment]::SetEnvironmentVariable("BIZCLINIK_APP_PASSWORD", $Password, "Machine")
[Environment]::SetEnvironmentVariable("BIZCLINIK_DB_PATH",
    (Join-Path $AppRoot "data\bizclinik.db"), "Machine")

Write-Step "Registering the Streamlit app as a Scheduled Task (auto-start at boot)"
$taskName = "BizClinikERP"
$action = New-ScheduledTaskAction `
    -Execute $venvPy `
    -Argument "-m streamlit run app/Home.py --server.headless true --server.port $Port --browser.gatherUsageStats false --server.address 127.0.0.1" `
    -WorkingDirectory $AppRoot

$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal | Out-Null


# ---- 9. Start services ----------------------------------------------------

Write-Step "Starting services"
Start-Service cloudflared
Start-ScheduledTask -TaskName $taskName

Write-Host ""
Write-Host "Done." -ForegroundColor Green
Write-Host "  Public URL : https://$Subdomain"
Write-Host "  Password   : $Password   (stored as BIZCLINIK_APP_PASSWORD env var)"
Write-Host ""
Write-Host "Health checks:"
Write-Host "  - Local app : curl http://localhost:$Port/_stcore/health   (expect: ok)"
Write-Host "  - Tunnel    : Get-Service cloudflared"
Write-Host "  - App       : Get-ScheduledTask BizClinikERP"
Write-Host ""
Write-Host "Logs:"
Write-Host "  - cloudflared : Event Viewer -> Applications and Services Logs"
Write-Host "  - Streamlit   : %SystemRoot%\Temp (under SYSTEM profile)"
