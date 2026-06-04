<#
 .SYNOPSIS
  Deploy BizClinik ERP behind a Cloudflare named tunnel using a Cloudflare
  API token instead of the interactive `cloudflared tunnel login` flow.

 .DESCRIPTION
  Use this when the dashboard's argotunnel OAuth page is broken or the
  domain DNS lives elsewhere. The script:
    1. Detects Python, creates venv, installs requirements, inits the DB
    2. Downloads cloudflared if missing
    3. Calls the Cloudflare API to find the zone + account
    4. Creates a named tunnel `bizclinik-erp` (or reuses existing)
    5. Writes the credentials.json that cloudflared needs
    6. Creates a proxied CNAME `<sub>.<zone>` -> `<tunnel>.cfargotunnel.com`
    7. Writes the tunnel config.yml
    8. Installs cloudflared + Streamlit as Windows services and starts them

  Idempotent: safe to re-run. Will reuse the existing tunnel and update DNS.

 .PARAMETER Subdomain
   e.g. erp.hagai.online

 .PARAMETER Password
   Lock-screen password (env var BIZCLINIK_APP_PASSWORD).

 .PARAMETER ApiToken
   Cloudflare API token with Zone:DNS:Edit + Account:Cloudflare Tunnel:Edit
   for the zone in question.

 .EXAMPLE
   .\api_bootstrap.ps1 -Subdomain erp.hagai.online -Password 'xxx' -ApiToken 'CF_xxx'
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)] [string]$Subdomain,
    [Parameter(Mandatory = $true)] [string]$Password,
    [Parameter(Mandatory = $true)] [string]$ApiToken,
    [int]$Port = 8501,
    [string]$TunnelName = "bizclinik-erp",
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

if (-not (Test-Admin)) { throw "Run elevated." }

# Compute zone (everything after the first dot of the subdomain)
$idx = $Subdomain.IndexOf('.')
if ($idx -lt 0) { throw "Subdomain must include a zone, e.g. erp.hagai.online" }
$ZoneName = $Subdomain.Substring($idx + 1)
$Record = $Subdomain.Substring(0, $idx)

Write-Host "BizClinik ERP -- API bootstrap" -ForegroundColor Green
Write-Host "  Subdomain : $Subdomain  (zone=$ZoneName  record=$Record)"
Write-Host "  Tunnel    : $TunnelName"
Write-Host "  App root  : $AppRoot"
Write-Host "  Local port: $Port"

$apiHeaders = @{
    Authorization = "Bearer $ApiToken"
    "Content-Type" = "application/json"
}


# ---- 1. Python venv + deps ------------------------------------------------

Write-Step "Checking Python"
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { throw "Python not found on PATH." }
& $python --version

$venvPath = Join-Path $AppRoot "venv"
if (-not (Test-Path $venvPath)) { & $python -m venv $venvPath }
$venvPy  = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"
Write-Step "Installing requirements"
& $venvPy -m pip install --upgrade pip | Out-Null
& $venvPip install -r (Join-Path $AppRoot "requirements.txt")

Write-Step "Initialising SQLite database"
Push-Location $AppRoot
& $venvPy -m bizclinik_erp init
Pop-Location


# ---- 2. cloudflared download ---------------------------------------------

Write-Step "Ensuring cloudflared is installed"
$cfDir = "C:\Program Files (x86)\cloudflared"
$cfExe = Join-Path $cfDir "cloudflared.exe"
if (-not (Test-Path $cfExe)) {
    New-Item -ItemType Directory -Force -Path $cfDir | Out-Null
    $url = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Invoke-WebRequest -Uri $url -OutFile $cfExe -UseBasicParsing
}
$env:Path = $cfDir + ";" + $env:Path
& $cfExe --version


# ---- 3. Cloudflare API: zone + account ------------------------------------

Write-Step "Looking up Cloudflare zone $ZoneName"
$zr = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones?name=$ZoneName" -Headers $apiHeaders -Method Get
if (-not $zr.success -or -not $zr.result -or $zr.result.Count -eq 0) {
    throw "Zone $ZoneName not found via API. Check the token scope."
}
$zone = $zr.result[0]
$ZoneId = $zone.id
$AccountId = $zone.account.id
Write-Host "  account=$AccountId zone=$ZoneId status=$($zone.status)"


# ---- 4. Tunnel: find existing or create new -------------------------------

Write-Step "Finding/creating tunnel $TunnelName"
$listResp = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/cfd_tunnel?is_deleted=false" -Headers $apiHeaders -Method Get
$existing = $listResp.result | Where-Object { $_.name -eq $TunnelName -and -not $_.deleted_at }

if ($existing) {
    Write-Host "  Reusing existing tunnel: $($existing.id)"
    $TunnelId = $existing.id
    # Existing creds file?
    $cfHome = Join-Path $env:USERPROFILE ".cloudflared"
    New-Item -ItemType Directory -Force -Path $cfHome | Out-Null
    $credFile = Join-Path $cfHome "$TunnelId.json"
    if (-not (Test-Path $credFile)) {
        # We don't have the secret -- delete and recreate.
        Write-Host "  Credentials file missing for reused tunnel. Recreating tunnel."
        Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/cfd_tunnel/$TunnelId" -Headers $apiHeaders -Method Delete | Out-Null
        $existing = $null
    }
}

if (-not $existing) {
    # Generate 32-byte secret, base64
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $secretBytes = New-Object byte[] 32
    $rng.GetBytes($secretBytes)
    $TunnelSecret = [Convert]::ToBase64String($secretBytes)

    $body = @{
        name = $TunnelName
        tunnel_secret = $TunnelSecret
        config_src = "local"
    } | ConvertTo-Json -Depth 5

    $createResp = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/accounts/$AccountId/cfd_tunnel" -Headers $apiHeaders -Method Post -Body $body
    if (-not $createResp.success) {
        throw "Tunnel create failed: $($createResp.errors | ConvertTo-Json -Depth 5)"
    }
    $TunnelId = $createResp.result.id
    Write-Host "  Created tunnel: $TunnelId"

    $cfHome = Join-Path $env:USERPROFILE ".cloudflared"
    New-Item -ItemType Directory -Force -Path $cfHome | Out-Null
    $credFile = Join-Path $cfHome "$TunnelId.json"
    $credObj = @{
        AccountTag = $AccountId
        TunnelID = $TunnelId
        TunnelName = $TunnelName
        TunnelSecret = $TunnelSecret
    } | ConvertTo-Json -Depth 5
    Set-Content -Path $credFile -Value $credObj -Encoding UTF8 -Force
}


# ---- 5. DNS CNAME ---------------------------------------------------------

Write-Step "Configuring DNS CNAME $Subdomain -> $TunnelId.cfargotunnel.com"
$cnameTarget = "$TunnelId.cfargotunnel.com"
$dnsList = Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones/$ZoneId/dns_records?type=CNAME&name=$Subdomain" -Headers $apiHeaders -Method Get
$dnsExisting = $dnsList.result | Where-Object { $_.name -eq $Subdomain }
$dnsBody = @{
    type = "CNAME"
    name = $Record
    content = $cnameTarget
    proxied = $true
    ttl = 1
} | ConvertTo-Json -Depth 5
if ($dnsExisting) {
    Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones/$ZoneId/dns_records/$($dnsExisting.id)" -Headers $apiHeaders -Method Put -Body $dnsBody | Out-Null
    Write-Host "  Updated existing CNAME"
} else {
    Invoke-RestMethod -Uri "https://api.cloudflare.com/client/v4/zones/$ZoneId/dns_records" -Headers $apiHeaders -Method Post -Body $dnsBody | Out-Null
    Write-Host "  Created CNAME"
}


# ---- 6. config.yml --------------------------------------------------------

Write-Step "Writing tunnel config.yml"
$cfgPath = Join-Path $cfHome "config.yml"
@"
tunnel: $TunnelId
credentials-file: $credFile

ingress:
  - hostname: $Subdomain
    service: http://localhost:$Port
  - service: http_status:404
"@ | Out-File -FilePath $cfgPath -Encoding utf8 -Force


# ---- 7. cloudflared service ------------------------------------------------

Write-Step "Installing cloudflared as a Windows service"
$svc = Get-Service -Name "cloudflared" -ErrorAction SilentlyContinue
if ($svc) {
    Stop-Service cloudflared -ErrorAction SilentlyContinue
    & $cfExe service uninstall | Out-Null
}
& $cfExe --config $cfgPath service install


# ---- 8. SYSTEM env + Scheduled Task for Streamlit -------------------------

Write-Step "Setting SYSTEM env vars and registering ERP task"
[Environment]::SetEnvironmentVariable("BIZCLINIK_APP_PASSWORD", $Password, "Machine")
[Environment]::SetEnvironmentVariable("BIZCLINIK_DB_PATH",
    (Join-Path $AppRoot "data\bizclinik.db"), "Machine")

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


# ---- 9. Start services ----------------------------------------------------

Write-Step "Starting services"
Start-Service cloudflared
Start-ScheduledTask -TaskName $taskName

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host " PUBLIC URL : https://$Subdomain"
Write-Host " PASSWORD   : $Password"
Write-Host "================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "Health checks:"
Write-Host "  curl -I https://$Subdomain"
Write-Host "  Invoke-WebRequest http://localhost:$Port/_stcore/health"
Write-Host "  Get-Service cloudflared"
Write-Host "  Get-ScheduledTask BizClinikERP"
