#!/usr/bin/env bash
#
# One-command redeploy on Linux. Run as root:
#   bash /opt/bizclinik-erp/deploy/linux/update.sh
#
# Pulls latest code, installs deps, runs idempotent migration, restarts.
# Data in data/ is preserved. cloudflared is left running.

set -euo pipefail
APP_DIR="/opt/bizclinik-erp"
PORT="8501"

echo "==> Pulling latest code"
git -C "$APP_DIR" pull --ff-only

echo "==> Installing requirements"
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

echo "==> Idempotent DB migration"
sudo -u bizclinik env BIZCLINIK_DB_PATH="$APP_DIR/data/bizclinik.db" \
  sh -c "cd '$APP_DIR' && exec '$APP_DIR/venv/bin/python' -m bizclinik_erp init"

chown -R bizclinik:bizclinik "$APP_DIR"

echo "==> Restarting service"
systemctl restart bizclinik-erp

echo "==> Waiting for health"
for i in $(seq 1 30); do
  sleep 2
  if curl -fsS "http://localhost:$PORT/_stcore/health" 2>/dev/null | grep -q ok; then
    echo "Local health: ok"
    curl -fsS "https://erp.hagai.online/_stcore/health" 2>/dev/null && echo " (public ok)" || echo "(public warming up)"
    exit 0
  fi
done
echo "Not healthy yet. Check: journalctl -u bizclinik-erp -n 50"
exit 1
