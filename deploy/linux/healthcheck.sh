#!/usr/bin/env bash
# Self-hosted uptime watchdog for BizClinik ERP. Run by a systemd timer every
# few minutes. Checks the public health endpoints; on failure it (1) tries to
# restart the failed service, (2) re-checks, and (3) emails an alert if SMTP is
# configured. No external monitoring service / signup required.
#
# Env (optional, e.g. from /etc/bizclinik/backup.env or the unit):
#   HEALTH_URLS         space-separated URLs to check
#                       (default: erp + api + wendysrack tenant health)
#   ALERT_EMAIL         where to send alerts (uses SMTP_* via the app)
#   SMTP_HOST ...       same SMTP_* vars the app's notifications use
set -u

APP_DIR="/opt/bizclinik-erp"
PY="$APP_DIR/venv/bin/python"

DEFAULT_URLS="https://erp.hagai.online/_stcore/health \
https://api.hagai.online/health \
https://wendysrack-erp.hagai.online/_stcore/health"
URLS="${HEALTH_URLS:-$DEFAULT_URLS}"

# Map a hostname to the systemd service that backs it, for auto-restart.
service_for() {
  case "$1" in
    api.hagai.online) echo "bizclinik-api" ;;
    *) echo "bizclinik-erp" ;;
  esac
}

check() {  # url -> 0 if healthy
  curl -fsS --max-time 12 -o /dev/null "$1"
}

failures=""
for url in $URLS; do
  host="$(echo "$url" | sed -E 's#https?://([^/]+)/.*#\1#')"
  if check "$url"; then
    continue
  fi
  svc="$(service_for "$host")"
  echo "$(date -u +%FT%TZ) UNHEALTHY $url -> restarting $svc" >&2
  systemctl restart "$svc" 2>/dev/null || true
  sleep 8
  if check "$url"; then
    echo "$(date -u +%FT%TZ) RECOVERED $url after restarting $svc" >&2
  else
    failures="${failures}\n- ${url} (service ${svc} restarted, still failing)"
  fi
done

[ -z "$failures" ] && exit 0

# Still-failing endpoints: send an email alert if we can.
ALERT_EMAIL="${ALERT_EMAIL:-}"
if [ -n "$ALERT_EMAIL" ] && [ -n "${SMTP_HOST:-}" ]; then
  body="$(printf 'BizClinik ERP health check FAILED at %s UTC:%b\n' "$(date -u +%FT%TZ)" "$failures")"
  MSG="$body" TO="$ALERT_EMAIL" "$PY" - <<'PY' 2>/dev/null || true
import os, smtplib
from email.mime.text import MIMEText
host=os.environ.get("SMTP_HOST"); port=int(os.environ.get("SMTP_PORT","587"))
user=os.environ.get("SMTP_USER"); pw=os.environ.get("SMTP_PASS")
frm=os.environ.get("SMTP_FROM", user or "alerts@bizclinik"); to=os.environ["TO"]
m=MIMEText(os.environ["MSG"]); m["Subject"]="[BizClinik ERP] health alert"
m["From"]=frm; m["To"]=to
s=smtplib.SMTP(host,port,timeout=20); s.starttls()
if user and pw: s.login(user,pw)
s.sendmail(frm,[to],m.as_string()); s.quit()
print("alert sent")
PY
fi
printf 'health check failures:%b\n' "$failures" >&2
exit 1
