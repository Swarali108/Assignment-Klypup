#!/usr/bin/env bash
# AURELIA demo launcher.  ./demo.sh start | stop | status
# API on 127.0.0.1:8000 (uvicorn), web on :3000 (next start; it proxies /api to the API). PIDs live in api/state/.
# Sign-in: demo accounts are seeded on start. DATABASE_URL (Neon/Postgres) is read from .env if set; else SQLite.
set -euo pipefail
cd "$(dirname "$0")"
STATE=api/state
API_PORT=8000
WEB_PORT=3000
mkdir -p "$STATE"

listener() { lsof -ti ":$1" -sTCP:LISTEN 2>/dev/null | head -1 || true; }

start() {
  [ -x .venv/bin/python ] || { echo "Missing .venv - run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"; exit 1; }
  [ -d web/node_modules ] || { echo "Missing web/node_modules - run: (cd web && npm install)"; exit 1; }
  if [ -n "$(listener $API_PORT)" ] || [ -n "$(listener $WEB_PORT)" ]; then
    echo "Port $API_PORT or $WEB_PORT is already in use. Run ./demo.sh stop first."; exit 1
  fi
  # Create the tables and the three demo users (safe to repeat; never overwrites an existing user).
  .venv/bin/python -m api.seed_users > "$STATE/seed.log" 2>&1 || { echo "Could not set up the database - see $STATE/seed.log"; exit 1; }
  # Bound to the loopback address only: the API is reached through the web app, never from the network.
  .venv/bin/python -m uvicorn api.main:app --host 127.0.0.1 --port "$API_PORT" > "$STATE/api.log" 2>&1 &
  echo $! > "$STATE/api.pid"
  if [ ! -f web/.next/BUILD_ID ] || [ -n "$(find web/app web/lib web/components web/proxy.ts web/next.config.ts -newer web/.next/BUILD_ID -type f 2>/dev/null | head -1)" ]; then
    echo "Building web..."
    (cd web && npm run build > "../$STATE/web-build.log" 2>&1) || { echo "Web build failed - see $STATE/web-build.log"; exit 1; }
  fi
  (cd web && exec ./node_modules/.bin/next start -H 127.0.0.1 -p "$WEB_PORT") > "$STATE/web.log" 2>&1 &
  echo $! > "$STATE/web.pid"
  for _ in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$API_PORT/api/health" >/dev/null && curl -sf -o /dev/null "http://127.0.0.1:$WEB_PORT/login"; then
      echo "AURELIA is running:  http://localhost:$WEB_PORT   (sign in with admin@ / head@ / rm@ / viewer@ / new.rm@aurelia.demo, password demo1234; head@ is the Head of RMs, new.rm@ sees the first-sign-in setup guide)"; return
    fi
    sleep 1
  done
  echo "Started, but not answering yet. Check $STATE/api.log and $STATE/web.log"
}

stop() {
  for n in api web; do
    f="$STATE/$n.pid"
    if [ -f "$f" ]; then
      pid=$(cat "$f")
      # kill the recorded PID and anything still listening on that service's port
      kill "$pid" 2>/dev/null || true
      rm -f "$f"
    fi
  done
  # A leftover server of ours (uvicorn / next) still holding a port; anything else is left alone.
  for p in $API_PORT $WEB_PORT; do
    pid=$(listener "$p")
    if [ -n "$pid" ] && ps -o command= -p "$pid" | grep -Eq "uvicorn|next"; then kill "$pid" 2>/dev/null || true; fi
  done
  echo "Stopped."
}

status() {

  echo "api pid: $(listener $API_PORT)  web pid: $(listener $WEB_PORT)"
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  *) echo "usage: $0 start|stop|status"; exit 1 ;;
esac
