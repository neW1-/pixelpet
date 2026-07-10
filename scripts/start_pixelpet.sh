#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="${PIXELPET_RUN_DIR:-"$ROOT_DIR/.pixelpet"}"
PID_FILE="${PIXELPET_PID_FILE:-"$RUN_DIR/pixelpet.pid"}"
LOG_FILE="${PIXELPET_LOG_FILE:-"$RUN_DIR/pixelpet.log"}"
STARTUP_WAIT_SECONDS="${PIXELPET_STARTUP_WAIT_SECONDS:-2}"

CONFIG_FILE="${PIXELPET_CONFIG:-"$ROOT_DIR/config.toml"}"
PIXELPET_BIN="${PIXELPET_BIN:-"$ROOT_DIR/.venv/bin/pixelpet"}"

if [[ ! -x "$PIXELPET_BIN" ]]; then
  echo "pixelpet binary not found: $PIXELPET_BIN" >&2
  echo "Create the local venv first: python3 -m venv .venv && .venv/bin/python -m pip install -e ." >&2
  exit 1
fi

mkdir -p "$RUN_DIR"

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE")"
  if [[ -n "$OLD_PID" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "PixelPet is already running with pid $OLD_PID"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

cd "$ROOT_DIR"

CMD=("$PIXELPET_BIN" run --config "$CONFIG_FILE")

if [[ -n "${PIXELPET_ADDRESS:-}" ]]; then
  CMD+=(--address "$PIXELPET_ADDRESS")
fi
if [[ -n "${PIXELPET_PET:-}" ]]; then
  CMD+=(--pet "$PIXELPET_PET")
fi
if [[ -n "${PIXELPET_BRIGHTNESS:-}" ]]; then
  CMD+=(--brightness "$PIXELPET_BRIGHTNESS")
fi
if [[ -n "${PIXELPET_POLL_SECONDS:-}" ]]; then
  CMD+=(--poll-seconds "$PIXELPET_POLL_SECONDS")
fi
if [[ -n "${PIXELPET_DONE_TIMEOUT_SECONDS:-}" ]]; then
  CMD+=(--done-timeout-seconds "$PIXELPET_DONE_TIMEOUT_SECONDS")
fi

LOG_START_SIZE=0
if [[ -f "$LOG_FILE" ]]; then
  LOG_START_SIZE="$(wc -c <"$LOG_FILE")"
fi

nohup "${CMD[@]}" >>"$LOG_FILE" 2>&1 &

PID="$!"
echo "$PID" >"$PID_FILE"
sleep "$STARTUP_WAIT_SECONDS"
if ! kill -0 "$PID" 2>/dev/null; then
  rm -f "$PID_FILE"
  echo "PixelPet failed to start. Recent log output:" >&2
  tail -c "+$((LOG_START_SIZE + 1))" "$LOG_FILE" 2>/dev/null | tail -n 20 >&2 || true
  exit 1
fi
echo "PixelPet started with pid $PID"
echo "Log: $LOG_FILE"
