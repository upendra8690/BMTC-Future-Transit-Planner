#!/bin/sh
# Container entry point. Starts the planner with uvicorn after loading its data.
#
#   DEMO_MODE=1            a demonstration server: it serves the invented demo feeds, loaded here
#                          (SEED_DEMO_FEED=0 turns the loading off). Without it the server shows real data only.
#   LOAD_COMMUNITY_METRO   1 by default: load the community Namma Metro timetable (scripts/load_community_metro.py)
#                          if the database does not have it. The image already holds it, so this is instant there.
#
# On Render only Render's own proxy can reach the container, so when FORWARDED_ALLOW_IPS is still the image default
# it is widened to "*". uvicorn then trusts X-Forwarded-Proto (so HTTPS is recognised and HSTS is sent).
# Render does not remove an X-Forwarded-For header sent by the visitor, so its first entry can be forged. The rate
# limit therefore counts visitors by CF-Connecting-IP on Render, which Render's Cloudflare edge sets and a visitor
# cannot (CLIENT_IP_HEADER; see backend/app/security.py). Everywhere else (Docker Compose with Caddy) the configured
# values are kept.
# Render's free disk is erased on every restart, so with SQLite the app is told its storage is temporary
# (EPHEMERAL_STORAGE) and says so to passengers.
set -eu

if [ "${RENDER:-}" = "true" ]; then
  if [ "${FORWARDED_ALLOW_IPS:-127.0.0.1}" = "127.0.0.1" ]; then
    FORWARDED_ALLOW_IPS="*"
  fi
  export CLIENT_IP_HEADER="${CLIENT_IP_HEADER:-CF-Connecting-IP}"
  case "${DATABASE_URL:-}" in
    postgres*) ;;
    *) export EPHEMERAL_STORAGE="${EPHEMERAL_STORAGE:-1}" ;;
  esac
fi

demo="${DEMO_MODE:-0}"
seed="${SEED_DEMO_FEED:-$demo}"
if [ "$demo" = "1" ] && [ "$seed" = "1" ]; then
  python scripts/seed_demo_feed.py || echo "seed_demo_feed failed; starting without the demo feed" >&2
fi
if [ "${LOAD_COMMUNITY_METRO:-1}" = "1" ]; then
  python scripts/load_community_metro.py || echo "load_community_metro failed; starting without it" >&2
fi

# --no-access-log: uvicorn's access log would record every search text and "stops near me" coordinates with the
# visitor's address. The planner's own log keeps method, path (no query string), status and time for changes only.
exec uvicorn app.main:create_app --factory --app-dir backend --host 0.0.0.0 --port "${PORT:-8000}" --no-access-log \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
