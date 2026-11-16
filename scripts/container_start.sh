#!/bin/sh
# Container entry point. Starts the planner with uvicorn, after two optional steps for hosted demos.
#
#   SEED_DEMO_FEED=1   load the SYNTHETIC demo feed when the database has no imports (scripts/seed_demo_feed.py).
#   On Render (RENDER=true), SEED_DEMO_FEED defaults to 1, because the free disk starts empty after every restart.
#
# On Render only Render's own proxy can reach the container, so when FORWARDED_ALLOW_IPS is still the image default
# it is widened to "*". uvicorn then reads each visitor's address from X-Forwarded-For, and the per-client rate limit
# applies per visitor instead of to the proxy. Everywhere else (Docker Compose with Caddy) the configured value is kept.
set -eu

if [ "${RENDER:-}" = "true" ] && [ "${FORWARDED_ALLOW_IPS:-127.0.0.1}" = "127.0.0.1" ]; then
  FORWARDED_ALLOW_IPS="*"
fi

seed="${SEED_DEMO_FEED:-}"
if [ -z "$seed" ] && [ "${RENDER:-}" = "true" ]; then
  seed=1
fi
if [ "$seed" = "1" ]; then
  python scripts/seed_demo_feed.py || echo "seed_demo_feed failed; starting without the demo feed" >&2
fi

exec uvicorn app.main:create_app --factory --app-dir backend --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
