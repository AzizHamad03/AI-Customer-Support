#!/usr/bin/env bash
set -euo pipefail

python -u manage.py process_document_jobs &
worker_pid=$!

gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers 1 \
  --threads 4 \
  --timeout 180 \
  --access-logfile - \
  --error-logfile - &
web_pid=$!

cleanup() {
  kill "$worker_pid" "$web_pid" 2>/dev/null || true
  wait "$worker_pid" "$web_pid" 2>/dev/null || true
}

trap cleanup EXIT
trap 'exit 0' TERM INT

wait -n "$worker_pid" "$web_pid"
exit 1