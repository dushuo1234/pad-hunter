#!/usr/bin/env bash
# Start / stop / status for Pad Hunter listing-time / listing-signal scanner.
set -euo pipefail
DIR=/workspace/project-monitor
PIDFILE="$DIR/listing_scan.pid"
LOG="$DIR/listing_scan_daemon.log"
PY="$DIR/listing_scan_daemon.py"
INTERVAL="${LISTING_SCAN_INTERVAL:-900}"
WORKERS="${LISTING_SCAN_WORKERS:-12}"

cd "$DIR"

is_running() {
  if [[ ! -f "$PIDFILE" ]]; then
    return 1
  fi
  local pid
  pid="$(tr -d ' \n' < "$PIDFILE")"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "listing_scan_daemon.py"; then
      return 0
    fi
  fi
  return 1
}

cmd_start() {
  if is_running; then
    echo "already running pid=$(cat "$PIDFILE") interval=${INTERVAL}s workers=${WORKERS} log=$LOG"
    exit 0
  fi
  rm -f "$PIDFILE"
  nohup python3 "$PY" --daemon --interval "$INTERVAL" --workers "$WORKERS" --publish >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.5
  if is_running; then
    echo "started pid=$(cat "$PIDFILE") interval=${INTERVAL}s workers=${WORKERS} log=$LOG"
  else
    echo "ERROR failed to stay up; see $LOG" >&2
    tail -n 40 "$LOG" >&2 || true
    exit 1
  fi
}

cmd_stop() {
  if ! is_running; then
    echo "not running"
    rm -f "$PIDFILE"
    exit 0
  fi
  local pid
  pid="$(cat "$PIDFILE")"
  kill "$pid" 2>/dev/null || true
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$PIDFILE"
  echo "stopped pid=$pid"
}

cmd_status() {
  if is_running; then
    echo "running pid=$(cat "$PIDFILE")"
  else
    echo "not running"
  fi
  python3 "$PY" --status || true
}

cmd_once() {
  python3 "$PY" --once --workers "$WORKERS" --publish
}

cmd_restart() {
  cmd_stop || true
  cmd_start
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  once) cmd_once ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|once}"
    echo "Env: LISTING_SCAN_INTERVAL=900 LISTING_SCAN_WORKERS=12"
    exit 1
    ;;
esac
