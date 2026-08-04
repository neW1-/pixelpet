#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$ROOT_DIR/.pixelpet"
LOG_FILE="$LOG_DIR/streamdeck-command.log"

mkdir -p "$LOG_DIR"
cd "$ROOT_DIR"

{
  echo
  date "+%Y-%m-%d %H:%M:%S %z"
  echo "start_pixelpet.command starting"
  /bin/bash "$ROOT_DIR/scripts/start_streamdeck.sh"
} 2>&1 | tee -a "$LOG_FILE"
