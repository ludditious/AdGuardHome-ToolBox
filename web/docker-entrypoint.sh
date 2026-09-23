#!/bin/sh
# Copyright (C) 2026 https://ludditious.com/
#
#     This program is free software: you can redistribute it and/or modify
#     it under the terms of the GNU Affero General Public License as published by
#     the Free Software Foundation, either version 3 of the License, or
#     (at your option) any later version.
#
#     This program is distributed in the hope that it will be useful,
#     but WITHOUT ANY WARRANTY; without even the implied warranty of
#     MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#     GNU Affero General Public License for more details.
#
#     You should have received a copy of the GNU Affero General Public License
#     along with this program.  If not, see <https://www.gnu.org/licenses/>.

set -eu

mkdir -p /data /var/log
chmod +x /app/web/cron/cron-tick.sh

# Optional: CUSTOM_DNS=10.0.0.1 — internal DNS so local hostnames resolve in the container
if [ -n "${CUSTOM_DNS:-}" ]; then
  IFS=,
  for ns in $CUSTOM_DNS; do
    ns="$(echo "$ns" | tr -d ' ')"
    [ -n "$ns" ] && echo "nameserver $ns" >> /etc/resolv.conf
  done
  unset IFS
fi

SECRETS_FILE=/data/app-secrets.env

is_unset_secret() {
  case "${1:-}" in
    "" | change-me-in-production | change-cron-secret) return 0 ;;
    *) return 1 ;;
  esac
}

rand_hex() {
  python3 -c "import secrets; print(secrets.token_hex(${1:-32}))"
}

if [ -f "$SECRETS_FILE" ]; then
  # shellcheck disable=SC1090
  . "$SECRETS_FILE"
fi

if is_unset_secret "${SECRET_KEY:-}"; then
  SECRET_KEY="$(rand_hex 32)"
fi
if is_unset_secret "${CRON_SECRET:-}"; then
  CRON_SECRET="$(rand_hex 24)"
fi

umask 077
printf 'SECRET_KEY=%s\nCRON_SECRET=%s\n' "$SECRET_KEY" "$CRON_SECRET" > "$SECRETS_FILE"
chmod 600 "$SECRETS_FILE"
export SECRET_KEY CRON_SECRET

printf 'export CRON_SECRET=%s\nexport PORT=%s\n' "$CRON_SECRET" "${PORT:-8080}" > /app/web/cron/cron-env
chmod 600 /app/web/cron/cron-env

# Scheduling runs inside the app (see app/scheduler.py). Optional external cron:
if [ "${USE_SYSTEM_CRON:-false}" = "true" ]; then
  cat > /etc/cron.d/agh-sync <<'CRON'
* * * * * root . /app/web/cron/cron-env; /app/web/cron/cron-tick.sh >> /var/log/agh-sync-cron.log 2>&1

CRON
  chmod 0644 /etc/cron.d/agh-sync
  cron || true
fi

cd /app/web
# Trust X-Forwarded-* from reverse proxies (NPM, Traefik, etc.)
exec uvicorn app.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8080}" \
  --proxy-headers \
  --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}"
