#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${PIXELPET_RUN_DIR:-"$ROOT_DIR/.pixelpet"}"
PID_FILE="${PIXELPET_PID_FILE:-"$RUN_DIR/pixelpet.pid"}"

if [[ ! -f "$PID_FILE" ]]; then
  echo "PixelPet is not running; no pid file at $PID_FILE"
  exit 0
fi

PID="$(cat "$PID_FILE")"
if [[ -z "$PID" ]]; then
  rm -f "$PID_FILE"
  echo "Removed empty pid file."
  exit 0
fi

if ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "PixelPet process $PID is not running; removed stale pid file."
  exit 0
fi

kill "$PID"

for _ in {1..20}; do
  if ! kill -0 "$PID" 2>/dev/null; then
    rm -f "$PID_FILE"
    echo "PixelPet stopped."
    exit 0
  fi
  sleep 0.25
done

echo "PixelPet did not stop after 5 seconds; sending SIGKILL."
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "PixelPet stopped."

