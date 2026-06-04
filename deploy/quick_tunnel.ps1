<#
 .SYNOPSIS
  Finish the BizClinik ERP deploy using a Cloudflare Quick Tunnel.

 .DESCRIPTION
  Use this when the domain isn't on Cloudflare's nameservers (e.g. hagai.online
  is still managed by Hostinger). It bypasses the `cloudflared tunnel login` +
  DNS-route steps and instead runs a Cloudflare quick tunnel that publishes the
  Streamlit app at a random `https://*.trycloudflare.com` URL.

  Steps:
    1. Kill any leftover cloudflared processes from the previous failed run
    2. Set BIZCLINIK_APP_PASSWORD as a SYSTEM env var (survives reboots)
    3. Register Streamlit as a Scheduled Task and start it
    4. Wait for http://localhost:$Port/_stcore/health to return "ok"
    5. Register a Scheduled Task that runs `cloudflared tunnel --url http://localhost:$Port`
    6. Start the tunnel task, tail its log, extract the assigned public URL
    7. Print the URL

  Re-running this script reuses everything and just re-prints the latest URL.

 .EXAMPLE
   .\quick_tunnel.ps1 -Password 'uBJMglKjLhcWS4KkNjSe'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Password,
    [int]$Port = 8501,
    [string]$AppRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
)

$ErrorActionPreference = "Stop"

function Write-Step($msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = [Security.Principal.WindowsPrincipal]::new($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    throw "Run this in an elevated PowerShell."
}

$venvPy = Join-Path $AppRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    throw "venv not found at $venvPy. Run bootstrap.ps1 first to install Python deps."
}

$cfExe = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
if (-not (Test-Path $cfExe)) {
    throw "cloudflared not found at $cfExe. Run bootstrap.ps1 first."
}


# ---- 1. Kill leftover cloudflared (login was still polling) ----------------

Write-Step "Stopping any leftover cloudflared processes"
Get-Process cloudflared -ErrorAction SilentlyContinue | Stop-Process -Force


# ---- 2. SYSTEM env vars ----------------------------------------------------

Write-Step "Setting SYSTEM env vars"
[Environment]::SetEnvironmentVariable("BIZCLINIK_APP_PASSWORD", $Password, "Machine")
[Environment]::SetEnvironmentVariable("BIZCLINIK_DB_PATH",
    (Join-Path $AppRoot "data\bizclinik.db"), "Machine")


# ---- 3. Streamlit Scheduled Task ------------------------------------------

Write-Step "Registering BizClinikERP Streamlit task"
$taskName = "BizClinikERP"
$action = New-ScheduledTaskAction `
    -Execute $venvPy `
    -Argument "-m streamlit run app/Home.py --server.headless true --server.port $Port --browser.gatherUsageStats false --server.address 127.0.0.1" `
    -WorkingDirectory $AppRoot
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal | Out-Null
Start-ScheduledTask -TaskName $taskName


# ---- 4. Wait for Streamlit to be ready ------------------------------------

Write-Step "Waiting for Streamlit to come up on port $Port"
$ready = $false
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 1
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:$Port/_stcore/health" `
            -UseBasicParsing -TimeoutSec 2
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch { }
}
if (-not $ready) {
    throw "Streamlit did not come up within 60s. Check 'Get-ScheduledTask BizClinikERP'."
}
Write-Host "  Streamlit is up."


# ---- 5. cloudflared quick tunnel Scheduled Task ---------------------------

Write-Step "Registering CloudflaredQuickTunnel task"
$tunnelTask = "CloudflaredQuickTunnel"
$logDir = Join-Path $AppRoot "data"
$logFile = Join-Path $logDir "cloudflared.log"
if (Test-Path $logFile) { Remove-Item $logFile -Force }

# We wrap cloudflared in a tiny powershell launcher so we can redirect stderr
# to the log file (cloudflared writes its assigned URL to stderr).
$launcher = Join-Path $AppRoot "deploy\_run_tunnel.ps1"
@"
& 'C:\Program Files (x86)\cloudflared\cloudflared.exe' tunnel --no-autoupdate --url http://localhost:$Port *>&1 | Out-File -FilePath '$logFile' -Encoding utf8 -Append
"@ | Out-File -FilePath $launcher -Encoding utf8 -Force

$tunnelAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`""
$tunnelSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

if (Get-ScheduledTask -TaskName $tunnelTask -ErrorAction SilentlyContinue) {
    Stop-ScheduledTask -TaskName $tunnelTask -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $tunnelTask -Confirm:$false
}
Register-ScheduledTask -TaskName $tunnelTask -Action $tunnelAction -Trigger $trigger `
    -Settings $tunnelSettings -Principal $principal | Out-Null
Start-ScheduledTask -TaskName $tunnelTask


# ---- 6. Tail the log and extract the assigned URL -------------------------

Write-Step "Waiting for the public URL"
$publicUrl = $null
for ($i = 1; $i -le 60; $i++) {
    Start-Sleep -Seconds 1
    if (-not (Test-Path $logFile)) { continue }
    $content = Get-Content $logFile -Raw -ErrorAction SilentlyContinue
    if ($content -and ($content -match "https://[a-z0-9\-]+\.trycloudflare\.com")) {
        $publicUrl = $Matches[0]
        break
    }
}

Write-Host ""
if ($publicUrl) {
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host " PUBLIC URL : $publicUrl" -ForegroundColor Green
    Write-Host " PASSWORD   : $Password" -ForegroundColor Green
    Write-Host "================================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Open the URL, sign in with the password, share with whoever needs access."
    Write-Host "Note: a quick-tunnel URL changes whenever cloudflared restarts (e.g. after reboot)."
    Write-Host "To get a stable URL, move hagai.online DNS to Cloudflare and run deploy\bootstrap.ps1 instead."
} else {
    Write-Host "Could not extract the public URL within 60s. Inspect the log:" -ForegroundColor Yellow
    Write-Host "  $logFile"
    Write-Host "Or run: Get-Content '$logFile' -Tail 40"
}
