<#
 .SYNOPSIS
  Install BizClinik ERP (Streamlit) and cloudflared as proper Windows
  services using NSSM. Replaces the legacy Scheduled Task approach so we
  get auto-restart on failure, structured logs with rotation, and the
  standard `Get-Service / Restart-Service` workflow.

 .DESCRIPTION
  Steps:
    1. Download NSSM (https://nssm.cc/release/nssm-2.24.zip) if not present.
    2. Stop+remove any existing CloudflaredTunnel / BizClinikERP scheduled
       tasks (from the older api_bootstrap.ps1 path).
    3. nssm install BizClinikERP    -- venv python running streamlit.
    4. nssm install CloudflaredTunnel -- cloudflared.exe tunnel run.
    5. Configure stdout/stderr to C:\opt\bizclinik-erp\logs with rotation.
    6. Start-Service both, poll http://localhost:8501/_stcore/health.
    7. Print the public URL.

 .PARAMETER Subdomain
   e.g. erp.hagai.online

 .PARAMETER Password
   BIZCLINIK_APP_PASSWORD value injected as an env var on the service.

 .PARAMETER AppRoot
   Path to the bizclinik-erp checkout. Defaults to the parent of this
   script's directory.

 .EXAMPLE
   .\install_services.ps1 -Subdomain erp.hagai.online -Password 'xxx'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Subdomain,
    [Parameter(Mandatory = $true)] [string]$Password,
    [string]$AppRoot = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)),
    [int]$Port = 8501,
    [string]$LogDir = "C:\opt\bizclinik-erp\logs",
    [string]$NssmDir = "C:\Program Files\nssm",
    [string]$CloudflaredExe = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
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

if (-not (Test-Admin)) { throw "Run elevated." }

Write-Host "BizClinik ERP -- NSSM service install" -ForegroundColor Green
Write-Host "  Subdomain : $Subdomain"
Write-Host "  App root  : $AppRoot"
Write-Host "  Log dir   : $LogDir"
Write-Host "  Port      : $Port"

$venvPy = Join-Path $AppRoot "venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    throw "venv python not found at $venvPy. Run api_bootstrap.ps1 first to create the venv."
}

$dbPath = Join-Path $AppRoot "data\bizclinik.db"

# Make sure the log dir exists.
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$streamlitLog = Join-Path $LogDir "streamlit.log"
$cloudflaredLog = Join-Path $LogDir "cloudflared.log"


# ---- 1. NSSM ------------------------------------------------------------

Write-Step "Ensuring NSSM is installed"
$nssmExe = Join-Path $NssmDir "nssm.exe"

# Prefer NSSM already on PATH (e.g. installed via Chocolatey)
$pathNssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source

# Next, look for the bundled copy in deploy\bin\nssm.exe (shipped with the repo
# so we don't depend on nssm.cc being up).
$bundledNssm = Join-Path $PSScriptRoot "bin\nssm.exe"

if ($pathNssm) {
    $nssmExe = $pathNssm
    Write-Host "  Using existing NSSM at $nssmExe"
} elseif (Test-Path $bundledNssm) {
    New-Item -ItemType Directory -Force -Path $NssmDir | Out-Null
    Copy-Item -Force $bundledNssm $nssmExe
    Write-Host "  Installed bundled NSSM to $nssmExe"
} elseif (-not (Test-Path $nssmExe)) {
    # Fallback chain: Chocolatey -> nssm.cc -> GitHub mirror
    $installed = $false
    if (Get-Command choco -ErrorAction SilentlyContinue) {
        Write-Host "  Installing NSSM via Chocolatey..."
        & choco install nssm -y --no-progress | Out-Null
        $pathNssm = (Get-Command nssm -ErrorAction SilentlyContinue).Source
        if ($pathNssm) {
            $nssmExe = $pathNssm
            $installed = $true
        }
    }
    if (-not $installed) {
        $tmpZip = Join-Path $env:TEMP "nssm-2.24.zip"
        $tmpExtract = Join-Path $env:TEMP "nssm-2.24"
        if (Test-Path $tmpExtract) { Remove-Item -Recurse -Force $tmpExtract }
        $urls = @(
            "https://nssm.cc/release/nssm-2.24.zip",
            "https://github.com/kirillkovalenko/nssm/releases/download/v2.24/nssm-2.24.zip"
        )
        $downloaded = $false
        foreach ($u in $urls) {
            try {
                Write-Host "  Trying $u"
                Invoke-WebRequest -Uri $u -OutFile $tmpZip -UseBasicParsing -TimeoutSec 30
                $downloaded = $true
                break
            } catch {
                Write-Host "    failed: $($_.Exception.Message)"
            }
        }
        if (-not $downloaded) {
            throw "Could not download NSSM from any source. Install manually: 'choco install nssm -y' then re-run."
        }
        Write-Host "  Extracting..."
        Expand-Archive -Path $tmpZip -DestinationPath $env:TEMP -Force
        New-Item -ItemType Directory -Force -Path $NssmDir | Out-Null
        $src64 = Join-Path $tmpExtract "win64\nssm.exe"
        $src32 = Join-Path $tmpExtract "win32\nssm.exe"
        if (Test-Path $src64) {
            Copy-Item $src64 $nssmExe -Force
        } elseif (Test-Path $src32) {
            Copy-Item $src32 $nssmExe -Force
        } else {
            throw "Could not find nssm.exe in extracted archive at $tmpExtract"
        }
        Remove-Item -Recurse -Force $tmpExtract -ErrorAction SilentlyContinue
        Remove-Item -Force $tmpZip -ErrorAction SilentlyContinue
    }
}
Write-Host "  NSSM: $nssmExe"


# ---- 2. Remove legacy Scheduled Tasks -----------------------------------

Write-Step "Removing legacy Scheduled Tasks (if any)"
foreach ($t in @("BizClinikERP", "CloudflaredTunnel")) {
    if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
        Write-Host "  Unregistering scheduled task $t"
        Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
    }
}

# Stop+remove existing NSSM services so we can redeploy cleanly.
function Remove-NssmService($name) {
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "  Stopping existing service $name"
        Stop-Service $name -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
        & $nssmExe remove $name confirm | Out-Null
    }
}
Remove-NssmService "BizClinikERP"
Remove-NssmService "CloudflaredTunnel"


# ---- 3. Install BizClinikERP via NSSM -----------------------------------

Write-Step "Installing BizClinikERP service"
# -u forces unbuffered Python output so NSSM log captures lines immediately.
# --server.fileWatcherType=none disables Streamlit's watchdog file watcher
# (it crashes under the SYSTEM service context, killing the process).
# --server.runOnSave=false matches that intent.
$streamlitArgs = @(
    "-u", "-m", "streamlit", "run", "app/Home.py",
    "--server.headless=true",
    "--server.port=$Port",
    "--server.address=127.0.0.1",
    "--server.enableCORS=false",
    "--server.enableXsrfProtection=false",
    "--server.fileWatcherType=none",
    "--server.runOnSave=false",
    "--browser.gatherUsageStats=false"
) -join " "

& $nssmExe install BizClinikERP $venvPy $streamlitArgs | Out-Null
& $nssmExe set BizClinikERP AppDirectory $AppRoot | Out-Null
& $nssmExe set BizClinikERP DisplayName "BizClinik ERP (Streamlit)" | Out-Null
& $nssmExe set BizClinikERP Description "BizClinik ERP Streamlit app on port $Port" | Out-Null
& $nssmExe set BizClinikERP Start SERVICE_AUTO_START | Out-Null

# Inject env vars. NSSM AppEnvironmentExtra takes NAME=VALUE pairs.
# PYTHONUNBUFFERED=1 belt-and-braces with -u; PYTHONIOENCODING=utf-8 avoids
# crashes on the Naira sign in log output.
$envExtra = @(
    "BIZCLINIK_APP_PASSWORD=$Password",
    "BIZCLINIK_DB_PATH=$dbPath",
    "PYTHONUNBUFFERED=1",
    "PYTHONIOENCODING=utf-8"
)
& $nssmExe set BizClinikERP AppEnvironmentExtra $envExtra | Out-Null

# Logging with rotation (10 MB).
& $nssmExe set BizClinikERP AppStdout $streamlitLog | Out-Null
& $nssmExe set BizClinikERP AppStderr $streamlitLog | Out-Null
& $nssmExe set BizClinikERP AppRotateFiles 1 | Out-Null
& $nssmExe set BizClinikERP AppRotateOnline 1 | Out-Null
& $nssmExe set BizClinikERP AppRotateBytes 10485760 | Out-Null

# Restart throttling: 5s pause, restart on any non-zero exit.
& $nssmExe set BizClinikERP AppRestartDelay 5000 | Out-Null
& $nssmExe set BizClinikERP AppExit Default Restart | Out-Null


# ---- 4. Install CloudflaredTunnel via NSSM ------------------------------

Write-Step "Installing CloudflaredTunnel service"
if (-not (Test-Path $CloudflaredExe)) {
    throw "cloudflared.exe not found at $CloudflaredExe. Run api_bootstrap.ps1 first."
}
$cfHome = Join-Path $env:USERPROFILE ".cloudflared"
$cfgPath = Join-Path $cfHome "config.yml"
if (-not (Test-Path $cfgPath)) {
    throw "cloudflared config.yml not found at $cfgPath. Run api_bootstrap.ps1 first."
}

$cfArgs = "--no-autoupdate --config `"$cfgPath`" tunnel run"
& $nssmExe install CloudflaredTunnel $CloudflaredExe $cfArgs | Out-Null
& $nssmExe set CloudflaredTunnel AppDirectory (Split-Path -Parent $CloudflaredExe) | Out-Null
& $nssmExe set CloudflaredTunnel DisplayName "Cloudflare Tunnel (BizClinik ERP)" | Out-Null
& $nssmExe set CloudflaredTunnel Description "cloudflared tunnel run for BizClinik ERP" | Out-Null
& $nssmExe set CloudflaredTunnel Start SERVICE_AUTO_START | Out-Null
& $nssmExe set CloudflaredTunnel AppStdout $cloudflaredLog | Out-Null
& $nssmExe set CloudflaredTunnel AppStderr $cloudflaredLog | Out-Null
& $nssmExe set CloudflaredTunnel AppRotateFiles 1 | Out-Null
& $nssmExe set CloudflaredTunnel AppRotateOnline 1 | Out-Null
& $nssmExe set CloudflaredTunnel AppRotateBytes 10485760 | Out-Null
& $nssmExe set CloudflaredTunnel AppRestartDelay 5000 | Out-Null
& $nssmExe set CloudflaredTunnel AppExit Default Restart | Out-Null


# ---- 5. Start services and poll health ----------------------------------

Write-Step "Starting services"
Start-Service BizClinikERP
Start-Service CloudflaredTunnel

Write-Step "Waiting for http://localhost:$Port/_stcore/health (timeout 60s)"
$healthUrl = "http://localhost:$Port/_stcore/health"
$deadline = (Get-Date).AddSeconds(60)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    try {
        $resp = Invoke-WebRequest -Uri $healthUrl -UseBasicParsing -TimeoutSec 5
        if ($resp.StatusCode -eq 200 -and $resp.Content -match "ok") {
            $healthy = $true
            break
        }
    } catch {
        # not ready yet
    }
    Start-Sleep -Seconds 2
}

if (-not $healthy) {
    Write-Host "  Health check did NOT pass within 60s." -ForegroundColor Yellow
    Write-Host "  Inspect logs at $streamlitLog" -ForegroundColor Yellow
} else {
    Write-Host "  Health check passed." -ForegroundColor Green
}


# ---- 6. Done ------------------------------------------------------------

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host " PUBLIC URL : https://$Subdomain"
Write-Host " LOCAL HEAL : $healthUrl"
Write-Host " LOG DIR    : $LogDir"
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Manage services with:"
Write-Host "  Get-Service BizClinikERP, CloudflaredTunnel"
Write-Host "  Restart-Service BizClinikERP"
Write-Host "  Get-Content $streamlitLog -Tail 50 -Wait"
