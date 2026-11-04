#!/usr/bin/env bash
# Start / stop / restart / status / ensure for Pad Hunter TapeRobot/TapeOut CA watcher.
set -euo pipefail
DIR=/workspace/project-monitor
PIDFILE="$DIR/tapeout_watch.pid"
LOG="$DIR/tapeout_watch.log"
PY="$DIR/tapeout_watch.py"
# Prefer venv python (pycryptodome); fall back to system
PYTHON="$DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
INTERVAL="${TAPEOUT_WATCH_INTERVAL:-2}"

cd "$DIR"

is_running() {
  if [[ ! -f "$PIDFILE" ]]; then
    return 1
  fi
  local pid
  pid="$(tr -d ' \n' < "$PIDFILE")"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "tapeout_watch.py"; then
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
  rm -f "$PIDFILE"
  # Refresh watchlists before start (best-effort)
  nohup "$PYTHON" "$PY" --interval "$INTERVAL" >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.6
  if is_running; then
    echo "started pid=$(cat "$PIDFILE") interval=${INTERVAL}s log=$LOG"
  else
    echo "ERROR failed to stay up; see $LOG" >&2
    tail -n 50 "$LOG" >&2 || true
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
  cat "$DIR/tapeout_watch_status.json" 2>/dev/null || true
}

cmd_restart() {
  cmd_stop || true
  cmd_start
}

cmd_ensure() {
  if is_running; then
    echo "ok pid=$(cat "$PIDFILE")"
    exit 0
  fi
  cmd_start
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  ensure) cmd_ensure ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|ensure}"
    echo "Env: TAPEOUT_WATCH_INTERVAL=2 (seconds)"
    exit 1
    ;;
esac
