# Trakit365 ERP — Linux deployment (the permanent home)

Why Linux: `systemd` supervises the app properly. If Streamlit ever crashes,
`Restart=always` brings it back in ~3 seconds — no watchdog, no NSSM, no
scheduled-task hacks, no 90-second hangs. The whole class of "process died,
502" problems we hit on Windows simply does not happen here.

## First-time setup (≈5 minutes)

On a fresh Ubuntu 24.04 box, as root:

```bash
# 1. Clone (or just download setup.sh)
git clone --depth 1 https://github.com/Habayode/bizclinik-erp.git /opt/bizclinik-erp

# 2. Run the installer
bash /opt/bizclinik-erp/deploy/linux/setup.sh \
    --subdomain erp.hagai.online \
    --app-password 'YOUR_APP_PASSWORD' \
    --cf-token 'YOUR_CLOUDFLARE_API_TOKEN'
```

That single command:
- installs python/venv/cloudflared
- creates a dedicated `bizclinik` user
- builds the venv, installs deps
- pulls the seed DB (your Wendysrack data) if not already present
- initialises the DB + bootstraps the `admin` user
- creates/finds the Cloudflare named tunnel + proxied CNAME via API
- installs + starts both systemd services
- installs a nightly 02:30 DB backup timer
- waits for health and prints the URL

## Day-to-day

```bash
systemctl status bizclinik-erp cloudflared   # are they up?
journalctl -u bizclinik-erp -f               # live logs
systemctl restart bizclinik-erp              # instant, never hangs
```

## Deploy a new version

```bash
bash /opt/bizclinik-erp/deploy/linux/update.sh
```

Pulls latest from GitHub, migrates the DB idempotently, restarts. Data
preserved. ~30 seconds.

## Backups

Nightly snapshot at 02:30 into `/opt/bizclinik-erp/backups/`, 30-day
retention. Manual: `sudo -u bizclinik venv/bin/python scripts/backup.py snapshot`.
Restore: stop the service, `scripts/backup.py restore <path>`, start.

## Files

| File | Purpose |
|------|---------|
| `setup.sh` | first-time install (idempotent) |
| `update.sh` | redeploy latest code |
| `bizclinik-erp.service` | systemd unit for Streamlit |
| `cloudflared.service` | systemd unit for the tunnel |
