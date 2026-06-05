#!/usr/bin/env bash
#
# One-shot Linux setup for BizClinik ERP.
# Tested on Ubuntu 24.04 LTS. Run as root:
#
#   bash setup.sh \
#       --subdomain erp.hagai.online \
#       --app-password 'YOUR_APP_PASSWORD' \
#       --cf-token 'YOUR_CLOUDFLARE_API_TOKEN'
#
# What it does:
#   1. apt deps (python3, venv, git, curl)
#   2. dedicated 'bizclinik' system user
#   3. clone the repo into /opt/bizclinik-erp
#   4. venv + pip install
#   5. pull the seed DB (if data/bizclinik.db not already present)
#   6. init DB + bootstrap admin
#   7. install cloudflared, create/find the named tunnel via API, write
#      credentials + config.yml, create the proxied CNAME
#   8. install + enable both systemd services
#   9. wait for health, print status
#
# Idempotent: safe to re-run.

set -euo pipefail

SUBDOMAIN=""
APP_PASSWORD=""
CF_TOKEN=""
TUNNEL_NAME="bizclinik-erp"
REPO="https://github.com/Habayode/bizclinik-erp.git"
APP_DIR="/opt/bizclinik-erp"
PORT="8501"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --subdomain)    SUBDOMAIN="$2"; shift 2;;
    --app-password) APP_PASSWORD="$2"; shift 2;;
    --cf-token)     CF_TOKEN="$2"; shift 2;;
    --tunnel-name)  TUNNEL_NAME="$2"; shift 2;;
    *) echo "Unknown arg: $1"; exit 1;;
  esac
done

[[ -z "$SUBDOMAIN" ]]    && { echo "ERROR: --subdomain required"; exit 1; }
[[ -z "$APP_PASSWORD" ]] && { echo "ERROR: --app-password required"; exit 1; }
[[ -z "$CF_TOKEN" ]]     && { echo "ERROR: --cf-token required"; exit 1; }

ZONE_NAME="${SUBDOMAIN#*.}"          # erp.hagai.online -> hagai.online
RECORD="${SUBDOMAIN%%.*}"           # erp.hagai.online -> erp

step() { echo; echo "==> $1"; }

# ---- 1. apt deps --------------------------------------------------------
step "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git curl jq ca-certificates

# ---- 2. user ------------------------------------------------------------
step "Ensuring 'bizclinik' system user"
if ! id bizclinik &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin bizclinik
fi

# ---- 3. clone / update repo --------------------------------------------
step "Fetching application code"
if [[ -d "$APP_DIR/.git" ]]; then
  git -C "$APP_DIR" pull --ff-only
else
  git clone --depth 1 "$REPO" "$APP_DIR"
fi
mkdir -p "$APP_DIR/data" "$APP_DIR/logs" "$APP_DIR/backups"

# ---- 4. venv ------------------------------------------------------------
step "Creating venv + installing requirements"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/pip" install --quiet --upgrade pip
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ---- 5. seed DB (only if no DB yet) ------------------------------------
if [[ ! -f "$APP_DIR/data/bizclinik.db" ]]; then
  step "Pulling seed DB from repo"
  curl -fsSL "https://raw.githubusercontent.com/Habayode/bizclinik-erp/main/data/bizclinik.db" \
    -o "$APP_DIR/data/bizclinik.db" || echo "  (no seed DB in repo; starting fresh)"
fi

# ---- 6. .env + init -----------------------------------------------------
step "Writing .env + initialising database"
cat > "$APP_DIR/.env" <<EOF
BIZCLINIK_APP_PASSWORD=$APP_PASSWORD
EOF
chmod 600 "$APP_DIR/.env"
chown -R bizclinik:bizclinik "$APP_DIR"

# Must run from $APP_DIR so the bizclinik_erp package is importable
# (it's not pip-installed, just on the path via cwd).
sudo -u bizclinik env BIZCLINIK_APP_PASSWORD="$APP_PASSWORD" \
  BIZCLINIK_DB_PATH="$APP_DIR/data/bizclinik.db" \
  sh -c "cd '$APP_DIR' && exec '$APP_DIR/venv/bin/python' -m bizclinik_erp init --admin-password '$APP_PASSWORD'"

# ---- 7. cloudflared -----------------------------------------------------
step "Installing cloudflared"
if ! command -v cloudflared &>/dev/null; then
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64" \
    -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi
cloudflared --version

step "Creating/finding tunnel + DNS via Cloudflare API"
API="https://api.cloudflare.com/client/v4"
auth=(-H "Authorization: Bearer $CF_TOKEN" -H "Content-Type: application/json")

ZONE_JSON="$(curl -fsSL "${auth[@]}" "$API/zones?name=$ZONE_NAME")"
ZONE_ID="$(echo "$ZONE_JSON" | jq -r '.result[0].id')"
ACCOUNT_ID="$(echo "$ZONE_JSON" | jq -r '.result[0].account.id')"
[[ "$ZONE_ID" == "null" || -z "$ZONE_ID" ]] && { echo "ERROR: zone $ZONE_NAME not found / token lacks access"; exit 1; }
echo "  zone=$ZONE_ID account=$ACCOUNT_ID"

# Reuse a healthy tunnel if it has a creds file, else (re)create.
mkdir -p /etc/cloudflared
TUNNELS="$(curl -fsSL "${auth[@]}" "$API/accounts/$ACCOUNT_ID/cfd_tunnel?is_deleted=false")"
TUNNEL_ID="$(echo "$TUNNELS" | jq -r --arg n "$TUNNEL_NAME" '.result[] | select(.name==$n and .deleted_at==null) | .id' | head -1)"

if [[ -z "$TUNNEL_ID" || "$TUNNEL_ID" == "null" || ! -f "/etc/cloudflared/$TUNNEL_ID.json" ]]; then
  # delete stale tunnel of same name (can't reuse without the secret)
  if [[ -n "$TUNNEL_ID" && "$TUNNEL_ID" != "null" ]]; then
    curl -fsSL "${auth[@]}" -X DELETE "$API/accounts/$ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID/connections" >/dev/null || true
    curl -fsSL "${auth[@]}" -X DELETE "$API/accounts/$ACCOUNT_ID/cfd_tunnel/$TUNNEL_ID" >/dev/null || true
  fi
  SECRET="$(head -c 32 /dev/urandom | base64)"
  CREATE="$(curl -fsSL "${auth[@]}" -X POST "$API/accounts/$ACCOUNT_ID/cfd_tunnel" \
    --data "$(jq -nc --arg n "$TUNNEL_NAME" --arg s "$SECRET" '{name:$n, tunnel_secret:$s, config_src:"local"}')")"
  TUNNEL_ID="$(echo "$CREATE" | jq -r '.result.id')"
  [[ "$TUNNEL_ID" == "null" ]] && { echo "ERROR: tunnel create failed: $CREATE"; exit 1; }
  jq -nc --arg a "$ACCOUNT_ID" --arg t "$TUNNEL_ID" --arg n "$TUNNEL_NAME" --arg s "$SECRET" \
    '{AccountTag:$a, TunnelID:$t, TunnelName:$n, TunnelSecret:$s}' \
    > "/etc/cloudflared/$TUNNEL_ID.json"
fi
echo "  tunnel=$TUNNEL_ID"

# config.yml
cat > /etc/cloudflared/config.yml <<EOF
tunnel: $TUNNEL_ID
credentials-file: /etc/cloudflared/$TUNNEL_ID.json

ingress:
  - hostname: $SUBDOMAIN
    service: http://localhost:$PORT
  - service: http_status:404
EOF

# CNAME upsert
# NOTE: per-tenant subdomains are served by app code (auth._subdomain_from_request),
# but a *.<zone> wildcard cert is needed for TLS. Cloudflare free Universal SSL
# only covers one level (*.hagai.online), so nested *.erp.hagai.online has no
# cert. On a dedicated domain where tenants are one level deep
# (acme.example.com), add a single `*.example.com` proxied CNAME here and it
# works for free. Left as a single host for the current nested deploy.
TARGET="$TUNNEL_ID.cfargotunnel.com"
EXISTING="$(curl -fsSL "${auth[@]}" "$API/zones/$ZONE_ID/dns_records?type=CNAME&name=$SUBDOMAIN" | jq -r '.result[0].id')"
BODY="$(jq -nc --arg r "$RECORD" --arg c "$TARGET" '{type:"CNAME", name:$r, content:$c, proxied:true, ttl:1}')"
if [[ -n "$EXISTING" && "$EXISTING" != "null" ]]; then
  curl -fsSL "${auth[@]}" -X PUT "$API/zones/$ZONE_ID/dns_records/$EXISTING" --data "$BODY" >/dev/null
  echo "  CNAME updated -> $TARGET"
else
  curl -fsSL "${auth[@]}" -X POST "$API/zones/$ZONE_ID/dns_records" --data "$BODY" >/dev/null
  echo "  CNAME created -> $TARGET"
fi

# ---- 8. systemd services ------------------------------------------------
step "Installing systemd services"
cp "$APP_DIR/deploy/linux/bizclinik-erp.service" /etc/systemd/system/bizclinik-erp.service
cp "$APP_DIR/deploy/linux/cloudflared.service"  /etc/systemd/system/cloudflared.service
systemctl daemon-reload
systemctl enable --now bizclinik-erp
systemctl enable --now cloudflared

# ---- 9. nightly backup timer -------------------------------------------
step "Installing nightly backup timer"
# Optional offsite (Cloudflare R2) credentials live in /etc/bizclinik/backup.env
# (R2_ACCOUNT_ID, R2_BUCKET, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY,
# BIZCLINIK_BACKUP_PASSPHRASE). The '-' prefix makes the file optional: without
# it the snapshot still runs locally and just skips the R2 upload.
mkdir -p /etc/bizclinik
[ -f /etc/bizclinik/backup.env ] || cat > /etc/bizclinik/backup.env <<'ENVEOF'
# Cloudflare R2 offsite backup (fill in to enable encrypted offsite copies).
# R2_ACCOUNT_ID=
# R2_BUCKET=bizclinik-backups
# R2_ACCESS_KEY_ID=
# R2_SECRET_ACCESS_KEY=
# BIZCLINIK_BACKUP_PASSPHRASE=
ENVEOF
chmod 600 /etc/bizclinik/backup.env
chown bizclinik:bizclinik /etc/bizclinik/backup.env

cat > /etc/systemd/system/bizclinik-backup.service <<EOF
[Unit]
Description=BizClinik ERP nightly DB snapshot (+ encrypted offsite to R2)
[Service]
Type=oneshot
User=bizclinik
WorkingDirectory=$APP_DIR
Environment=BIZCLINIK_DB_PATH=$APP_DIR/data/bizclinik.db
EnvironmentFile=-/etc/bizclinik/backup.env
ExecStart=$APP_DIR/venv/bin/python scripts/backup.py snapshot
EOF
cat > /etc/systemd/system/bizclinik-backup.timer <<EOF
[Unit]
Description=Run BizClinik ERP backup nightly at 02:30
[Timer]
OnCalendar=*-*-* 02:30:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now bizclinik-backup.timer

# ---- 10. health ---------------------------------------------------------
step "Waiting for health"
ok=0
for i in $(seq 1 30); do
  sleep 2
  if curl -fsS "http://localhost:$PORT/_stcore/health" 2>/dev/null | grep -q ok; then
    ok=1; break
  fi
done

echo
if [[ "$ok" == "1" ]]; then
  echo "================================================================"
  echo " LOCAL HEALTH : ok"
  echo " PUBLIC URL   : https://$SUBDOMAIN"
  echo " APP PASSWORD : $APP_PASSWORD  (admin login)"
  echo "================================================================"
  echo
  echo "Manage:"
  echo "  systemctl status bizclinik-erp cloudflared"
  echo "  journalctl -u bizclinik-erp -f"
  echo "  systemctl restart bizclinik-erp"
else
  echo "Service did not become healthy. Check: journalctl -u bizclinik-erp -n 50"
  exit 1
fi
