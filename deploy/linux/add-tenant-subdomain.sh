#!/usr/bin/env bash
# Wire a free, one-level HTTPS subdomain for a BizClinik ERP tenant:
#   <slug>-erp.<zone>   ->  Cloudflare tunnel  ->  localhost:8501
#
# One level under the apex (e.g. acme-erp.hagai.online) is covered by the
# zone's free Universal SSL wildcard (*.<zone>), so no paid cert is needed.
# The app (auth._resolve_subdomain_slug) strips the "-erp" suffix and
# auto-selects tenant "<slug>", skipping the business picker.
#
# Usage:
#   CF_API_TOKEN=... ZONE_ID=... TUNNEL_ID=... ZONE=hagai.online \
#     ./add-tenant-subdomain.sh <slug> [port]
#
# Requires: curl, jq, python3, and the cloudflared systemd service.
set -euo pipefail

SLUG="${1:?usage: add-tenant-subdomain.sh <slug> [port]}"
PORT="${2:-8501}"
ZONE="${ZONE:?set ZONE (e.g. hagai.online)}"
ZONE_ID="${ZONE_ID:?set ZONE_ID}"
TUNNEL_ID="${TUNNEL_ID:?set TUNNEL_ID}"
TOKEN="${CF_API_TOKEN:?set CF_API_TOKEN}"
API="https://api.cloudflare.com/client/v4"
CONFIG="/etc/cloudflared/config.yml"

HOST="${SLUG}-erp.${ZONE}"
TARGET="${TUNNEL_ID}.cfargotunnel.com"
auth=(-H "Authorization: Bearer ${TOKEN}")

echo "==> Subdomain: ${HOST} -> http://localhost:${PORT}"

# 1) Proxied CNAME (idempotent upsert).
EXIST="$(curl -fsSL "${auth[@]}" "${API}/zones/${ZONE_ID}/dns_records?type=CNAME&name=${HOST}" | jq -r '.result[0].id')"
BODY="$(jq -nc --arg n "$HOST" --arg c "$TARGET" '{type:"CNAME", name:$n, content:$c, proxied:true, ttl:1}')"
if [[ -n "$EXIST" && "$EXIST" != "null" ]]; then
  curl -fsSL "${auth[@]}" -X PUT "${API}/zones/${ZONE_ID}/dns_records/${EXIST}" --data "$BODY" >/dev/null
  echo "    CNAME updated"
else
  curl -fsSL "${auth[@]}" -X POST "${API}/zones/${ZONE_ID}/dns_records" --data "$BODY" >/dev/null
  echo "    CNAME created"
fi

# 2) cloudflared ingress rule (idempotent insert before the 404 catch-all).
cp "$CONFIG" "${CONFIG}.bak.$(date +%s)"
python3 - "$CONFIG" "$HOST" "$PORT" <<'PY'
import sys
config, host, port = sys.argv[1], sys.argv[2], sys.argv[3]
s = open(config).read()
if f"hostname: {host}\n" in s:
    print("    ingress: already present"); raise SystemExit(0)
rule = f"  - hostname: {host}\n    service: http://localhost:{port}\n"
needle = "  - service: http_status:404\n"
if needle not in s:
    raise SystemExit("ERROR: no http_status:404 catch-all found in config.yml")
open(config, "w").write(s.replace(needle, rule + needle, 1))
print("    ingress: rule inserted")
PY

# 3) Reload cloudflared. NOTE: do NOT gate this on `cloudflared ingress
#    validate` — that subcommand can exit non-zero with only an advisory
#    message and silently skip the restart (which once left a stale config
#    serving 404s). Restart unconditionally, then assert a fresh PID.
OLD_PID="$(pgrep -x cloudflared || true)"
systemctl restart cloudflared
sleep 4
NEW_PID="$(pgrep -x cloudflared || true)"
systemctl is-active --quiet cloudflared || { echo "ERROR: cloudflared not active"; exit 1; }
[[ "$NEW_PID" != "$OLD_PID" ]] || echo "WARN: cloudflared PID unchanged ($NEW_PID) -- restart may not have cycled"
echo "    cloudflared reloaded (pid ${OLD_PID:-none} -> ${NEW_PID})"

# 4) Verify end-to-end over HTTPS.
sleep 2
CODE="$(curl -sS -o /dev/null -w '%{http_code}' "https://${HOST}/_stcore/health" || echo 000)"
echo "==> https://${HOST}/_stcore/health -> ${CODE}"
[[ "$CODE" == "200" ]] && echo "OK: ${HOST} is live over HTTPS." \
  || { echo "FAIL: expected 200 (give DNS a minute, then re-run)"; exit 1; }
