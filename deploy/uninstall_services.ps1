<#
 .SYNOPSIS
  Stop + remove the BizClinikERP and CloudflaredTunnel NSSM services and
  optionally clean up the log directory.

 .PARAMETER PurgeLogs
  If set, deletes the log directory after removing the services.

 .EXAMPLE
   .\uninstall_services.ps1
   .\uninstall_services.ps1 -PurgeLogs
#>
[CmdletBinding()]
param(
    [switch]$PurgeLogs,
    [string]$LogDir = "C:\opt\bizclinik-erp\logs",
    [string]$NssmDir = "C:\Program Files\nssm"
)

$ErrorActionPreference = "Stop"

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = [Security.Principal.WindowsPrincipal]::new($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}
if (-not (Test-Admin)) { throw "Run elevated." }

$nssmExe = Join-Path $NssmDir "nssm.exe"
if (-not (Test-Path $nssmExe)) {
    Write-Host "NSSM not found at $nssmExe -- falling back to sc.exe" -ForegroundColor Yellow
    $nssmExe = $null
}

function Remove-Svc($name) {
    $svc = Get-Service -Name $name -ErrorAction SilentlyContinue
    if (-not $svc) {
        Write-Host "  ${name}: not installed"
        return
    }
    Write-Host "  Stopping $name"
    Stop-Service $name -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    if ($nssmExe) {
        & $nssmExe remove $name confirm | Out-Null
    } else {
        sc.exe delete $name | Out-Null
    }
    Write-Host "  ${name}: removed"
}

Write-Host "==> Removing BizClinik services" -ForegroundColor Cyan
Remove-Svc "BizClinikERP"
Remove-Svc "CloudflaredTunnel"

if ($PurgeLogs) {
    if (Test-Path $LogDir) {
        Write-Host "==> Purging log dir $LogDir" -ForegroundColor Cyan
        Remove-Item -Recurse -Force $LogDir
    }
} else {
    Write-Host "Logs preserved at $LogDir (pass -PurgeLogs to delete)."
}

Write-Host "Done." -ForegroundColor Green
