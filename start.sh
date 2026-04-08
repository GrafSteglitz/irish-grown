#!/usr/bin/env bash
# start.sh — Launch Irish Grown with Gunicorn
# Usage:
#   ./start.sh              # production-style (4 workers, port 5000)
#   ./start.sh --dev        # single worker with reload for development
#   PORT=8080 ./start.sh    # custom port

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Resolve virtualenv ──────────────────────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.venv"
GUNICORN="$VENV_DIR/bin/gunicorn"

if [[ ! -x "$GUNICORN" ]]; then
  echo "ERROR: gunicorn not found at $GUNICORN"
  echo "Run:  uv add gunicorn"
  exit 1
fi

if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "WARNING: .env file not found — APP_KEY and other secrets may be missing"
fi

# ── Config ──────────────────────────────────────────────────────────────────
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-5000}"
WORKERS="${WORKERS:-4}"
LOG_LEVEL="${LOG_LEVEL:-info}"
ACCESS_LOG="${ACCESS_LOG:--}"   # '-' = stdout
ERROR_LOG="${ERROR_LOG:--}"

# ── Parse flags ─────────────────────────────────────────────────────────────
DEV_MODE=false
for arg in "$@"; do
  case "$arg" in
    --dev)  DEV_MODE=true ;;
    --help) echo "Usage: $0 [--dev]"; exit 0 ;;
    *)      echo "Unknown argument: $arg"; exit 1 ;;
  esac
done

# ── Launch ──────────────────────────────────────────────────────────────────
if $DEV_MODE; then
  echo "→ Starting in DEVELOPMENT mode (1 worker, auto-reload)"
  exec "$GUNICORN" app:app \
    --bind "${HOST}:${PORT}" \
    --workers 1 \
    --reload \
    --log-level debug \
    --access-logfile "$ACCESS_LOG" \
    --error-logfile  "$ERROR_LOG"
else
  echo "→ Starting in PRODUCTION mode (${WORKERS} workers on ${HOST}:${PORT})"
  exec "$GUNICORN" app:app \
    --bind "${HOST}:${PORT}" \
    --workers "$WORKERS" \
    --worker-class sync \
    --timeout 60 \
    --keep-alive 5 \
    --log-level "$LOG_LEVEL" \
    --access-logfile "$ACCESS_LOG" \
    --error-logfile  "$ERROR_LOG"
fi
