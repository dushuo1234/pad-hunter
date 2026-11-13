#!/usr/bin/env bash
# Poll Cloudflare manual launched marks → local prune + Pages publish.
set -euo pipefail
DIR=/workspace/project-monitor
PIDFILE="$DIR/sync_manual_launched.pid"
LOG="$DIR/sync_manual_launched.log"
PY="$DIR/sync_manual_launched.py"
PYTHON="$DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
INTERVAL="${SYNC_MANUAL_INTERVAL:-45}"

cd "$DIR"

is_running() {
  if [[ ! -f "$PIDFILE" ]]; then return 1; fi
  local pid; pid="$(tr -d ' \n' < "$PIDFILE")"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "sync_manual_launched.py" && return 0
  fi
  return 1
}

cmd_start() {
  if is_running; then
    echo "already running pid=$(cat "$PIDFILE") interval=${INTERVAL}s log=$LOG"
    exit 0
  fi
  rm -f "$PIDFILE"
  nohup "$PYTHON" "$PY" --daemon --interval "$INTERVAL" --publish >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.5
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
    rm -f "$PIDFILE"
    echo "not running"
    return 0
  fi
  kill "$(cat "$PIDFILE")" 2>/dev/null || true
  sleep 0.5
  rm -f "$PIDFILE"
  echo "stopped"
}

cmd_status() {
  if is_running; then
    echo "running pid=$(cat "$PIDFILE") interval=${INTERVAL}s log=$LOG"
  else
    echo "stopped"
    exit 1
  fi
}

cmd_ensure() {
  if is_running; then
    cmd_status
  else
    cmd_start
  fi
}

case "${1:-ensure}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status) cmd_status ;;
  ensure) cmd_ensure ;;
  *) echo "usage: $0 start|stop|restart|status|ensure" >&2; exit 2 ;;
esac
