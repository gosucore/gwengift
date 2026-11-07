#!/bin/bash
set -Eeuo pipefail

python -m alembic upgrade head
python -m app.seeds

python -m app.worker &
worker_pid=$!
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
api_pid=$!

shutdown() {
  kill -TERM "$api_pid" "$worker_pid" 2>/dev/null || true
  wait "$api_pid" "$worker_pid" 2>/dev/null || true
}
trap shutdown EXIT INT TERM

wait -n "$api_pid" "$worker_pid"
status=$?
echo "Application process exited with status ${status}; stopping its peer" >&2
exit "$status"
