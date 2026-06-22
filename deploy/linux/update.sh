#!/usr/bin/env bash
#
# One-command redeploy on Linux. Run as root:
#   bash /opt/bizclinik-erp/deploy/linux/update.sh
#
# Pulls latest code, installs deps, runs an idempotent schema migration across
# the default DB AND every tenant DB, then restarts the ERP + API services.
# Data in data/ is preserved. cloudflared is left running.

set -euo pipefail
APP_DIR="/opt/bizclinik-erp"
PORT="8501"

echo "==> Pulling latest code"
git -C "$APP_DIR" pull --ff-only

echo "==> Installing requirements"
"$APP_DIR/venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# Mirror the services' environment so migrations hit the REAL backend
# (Postgres in production via /etc/bizclinik/pg.env; SQLite otherwise). Both
# env files are optional so this stays correct on a plain SQLite box.
set -a
[ -f /etc/bizclinik/pg.env ] && . /etc/bizclinik/pg.env
[ -f "$APP_DIR/.env" ] && . "$APP_DIR/.env"
set +a

run_py() {
  sudo -u bizclinik env \
    PYTHONPATH="$APP_DIR" \
    BIZCLINIK_DB_BACKEND="${BIZCLINIK_DB_BACKEND:-}" \
    BIZCLINIK_DB_PATH="${BIZCLINIK_DB_PATH:-$APP_DIR/data/bizclinik.db}" \
    PGHOST="${PGHOST:-}" PGPORT="${PGPORT:-}" PGUSER="${PGUSER:-}" \
    PGPASSWORD="${PGPASSWORD:-}" PGDATABASE="${PGDATABASE:-}" \
    "$APP_DIR/venv/bin/python" -m bizclinik_erp "$@"
}

echo "==> Bootstrap/seed default DB (idempotent)"
run_py init

echo "==> Schema migration across default + every tenant DB"
run_py migrate

echo "==> Production hardening (NUMERIC money + ledger CHECK constraints; Postgres-only, idempotent)"
run_py harden

chown -R bizclinik:bizclinik "$APP_DIR"

# ---- User-manual PDF (served by the in-app Download button) -----------------
# Rebuilt on every deploy so it can't drift from docs/USER_MANUAL.md. Non-fatal:
# a failed build keeps the previous PDF and never blocks the deploy.
echo "==> Building user-manual PDF"
export PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright
"$APP_DIR/venv/bin/pip" install --quiet markdown playwright || true
"$APP_DIR/venv/bin/python" -m playwright install --with-deps chromium >/dev/null 2>&1 \
  || "$APP_DIR/venv/bin/python" -m playwright install chromium >/dev/null 2>&1 || true
chmod -R a+rX /opt/ms-playwright 2>/dev/null || true
if sudo -u bizclinik env PYTHONPATH="$APP_DIR" \
     PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
     "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/manual_to_pdf.py" \
     "$APP_DIR/docs/USER_MANUAL.md" "$APP_DIR/Trakit365_ERP_User_Manual.pdf"; then
  echo "Manual PDF rebuilt."
else
  echo "(PDF build failed — the in-app download keeps the previous copy)"
fi

# School-specific manual (served to school tenants). Non-fatal.
if [ -f "$APP_DIR/docs/USER_MANUAL_SCHOOL.md" ]; then
  if sudo -u bizclinik env PYTHONPATH="$APP_DIR" \
       PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright \
       "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/manual_to_pdf.py" \
       "$APP_DIR/docs/USER_MANUAL_SCHOOL.md" \
       "$APP_DIR/Trakit365_School_ERP_User_Manual.pdf"; then
    echo "School manual PDF rebuilt."
  else
    echo "(School PDF build failed — keeps previous copy)"
  fi
fi

echo "==> Restarting services"
systemctl restart bizclinik-erp
systemctl restart bizclinik-api 2>/dev/null || echo "(bizclinik-api not present — skipped)"

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
