#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "Creating virtualenv…"
  python3 -m venv .venv
  PY=.venv/bin/python
fi

"$PY" -m pip install -q -r requirements.txt

# Free the port: a stale server caches its LLM agent for the whole process, so
# editing .env does nothing until the old process is gone.
STALE="$(lsof -nP -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
if [ -n "$STALE" ]; then
  echo "Stopping stale server on port $PORT (PID $STALE)…"
  kill $STALE 2>/dev/null || true
  sleep 1
fi

exec env PORT="$PORT" "$PY" app.py
