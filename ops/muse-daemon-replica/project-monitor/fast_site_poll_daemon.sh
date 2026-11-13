#!/usr/bin/env bash
# Start / stop / status for Pad Hunter fast official-site poller.
set -euo pipefail
DIR=/workspace/project-monitor
PIDFILE="$DIR/fast_site_poll.pid"
LOG="$DIR/fast_site_poll.log"
PY="$DIR/fast_site_poll.py"
INTERVAL="${FAST_SITE_INTERVAL:-1}"

cd "$DIR"

is_running() {
  if [[ ! -f "$PIDFILE" ]]; then
    return 1
  fi
  local pid
  pid="$(tr -d ' \n' < "$PIDFILE")"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    # confirm it is our script
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "fast_site_poll.py"; then
      return 0
    fi
  fi
  return 1
}

cmd_start() {
  if is_running; then
    echo "already running pid=$(cat "$PIDFILE") interval=${INTERVAL}s log=$LOG"
    exit 0
  fi
  # stale pidfile
  rm -f "$PIDFILE"
  nohup python3 "$PY" --interval "$INTERVAL" >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.4
  if is_running; then
    echo "started pid=$(cat "$PIDFILE") interval=${INTERVAL}s log=$LOG"
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
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.3
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

cmd_restart() {
  cmd_stop || true
  cmd_start
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  *)
    echo "Usage: $0 {start|stop|restart|status}"
    echo "Env: FAST_SITE_INTERVAL=1 (seconds, clamp 1–60)"
    exit 1
    ;;
esac
