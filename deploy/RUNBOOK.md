# Trakit365 ERP — VPS deployment runbook

Target: **VPS1 (185.126.227.211:42014)** · subdomain **erp.hagai.online**

The whole thing is one PowerShell script. You RDP in once, clone from GitHub,
and run the bootstrap. The script handles Python deps, cloudflared install +
named tunnel + DNS, Windows services, and starts everything.

## Pre-reqs on the VPS

- Windows Server (already there)
- Python 3.11+ on PATH — `python --version` should respond. If not, install
  from https://www.python.org/downloads/windows/ (tick "Add Python to PATH").
- **Git** — install from https://git-scm.com/download/win if `git --version`
  doesn't work.
- **GitHub CLI** — install from https://cli.github.com/ (the repo is private,
  so you need credentials to clone).
- The hagai.online zone exists in your Cloudflare account.

## Steps

1. **RDP into VPS1**
   `mstsc /v:185.126.227.211:42014`

2. **Open PowerShell as Administrator** and authenticate to GitHub once:

   ```powershell
   gh auth login
   # Choose: GitHub.com → HTTPS → Login with a web browser
   # Paste the one-time code into the browser that opens.
   ```

3. **Clone the repo:**

   ```powershell
   New-Item -ItemType Directory -Force -Path C:\opt | Out-Null
   gh repo clone Habayode/bizclinik-erp C:\opt\bizclinik-erp
   cd C:\opt\bizclinik-erp
   ```

4. **Run the bootstrap:**

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\deploy\bootstrap.ps1 `
       -Subdomain "erp.hagai.online" `
       -Password  "uBJMglKjLhcWS4KkNjSe"
   ```

   The script is idempotent — safe to re-run if anything fails.

5. **Cloudflare login (one-time interactive step)**
   The script will pop a browser window asking you to sign in to Cloudflare
   and authorise the `hagai.online` zone. Click through; the script continues
   automatically.

6. **Wait ~30 seconds** for DNS propagation, then open
   **https://erp.hagai.online**. The lock screen appears.
   Password: `uBJMglKjLhcWS4KkNjSe`.

## Verifying after deploy

On VPS1 PowerShell:

```powershell
# Streamlit app
Invoke-WebRequest http://localhost:8501/_stcore/health    # body should be "ok"
Get-ScheduledTask BizClinikERP                            # State = Running

# Cloudflare tunnel
Get-Service cloudflared                                    # Status = Running
& 'C:\Program Files (x86)\cloudflared\cloudflared.exe' tunnel info bizclinik-erp
```

From any internet-connected machine:

```bash
curl -I https://erp.hagai.online        # expect 200/301
```

## Updating later

To deploy a new version:

```powershell
cd C:\opt\bizclinik-erp
Stop-ScheduledTask BizClinikERP
git pull
.\venv\Scripts\pip.exe install -r requirements.txt   # if deps changed
Start-ScheduledTask BizClinikERP
```

`data\bizclinik.db` is git-ignored so your live books survive every pull.

## Rolling back / tearing down

```powershell
Stop-ScheduledTask BizClinikERP
Unregister-ScheduledTask -TaskName BizClinikERP -Confirm:$false
Stop-Service cloudflared
& 'C:\Program Files (x86)\cloudflared\cloudflared.exe' service uninstall
& 'C:\Program Files (x86)\cloudflared\cloudflared.exe' tunnel delete bizclinik-erp
[Environment]::SetEnvironmentVariable("BIZCLINIK_APP_PASSWORD", $null, "Machine")
```

## Secrets

| Item                        | Value |
|-----------------------------|-------|
| Subdomain                   | erp.hagai.online |
| App password                | `uBJMglKjLhcWS4KkNjSe` |
| Tunnel name                 | bizclinik-erp |
| Local port                  | 8501 |
| DB path on VPS              | `C:\opt\bizclinik-erp\data\bizclinik.db` |
| Cloudflare creds (on VPS)   | `%USERPROFILE%\.cloudflared\` |
| Git remote                  | https://github.com/Habayode/bizclinik-erp (private) |
