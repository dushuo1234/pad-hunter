#!/usr/bin/env bash
# Start / stop / restart / status / ensure for near-realtime TG → Pad Hunter sync.
set -euo pipefail
DIR=/workspace/project-monitor
PIDFILE="$DIR/tg_push_fast.pid"
LOG="$DIR/tg_push_fast.log"
PY="$DIR/tg_push_fast.py"
PYTHON="$DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
INTERVAL="${TG_PUSH_FAST_INTERVAL:-60}"
LIMIT="${TG_PUSH_FAST_LIMIT:-40}"

cd "$DIR"

is_running() {
  if [[ ! -f "$PIDFILE" ]]; then return 1; fi
  local pid; pid="$(tr -d ' \n' < "$PIDFILE")"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "tg_push_fast.py" && return 0
  fi
  return 1
}

cmd_start() {
  if is_running; then
    echo "already running pid=$(cat "$PIDFILE") interval=${INTERVAL}s log=$LOG"
    exit 0
  fi
  rm -f "$PIDFILE"
  nohup "$PYTHON" "$PY" --daemon --interval "$INTERVAL" --limit "$LIMIT" >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.5
  if is_running; then
    echo "started pid=$(cat "$PIDFILE") interval=${INTERVAL}s limit=${LIMIT} log=$LOG"
  else
    echo "ERROR failed to stay up; see $LOG" >&2
    tail -n 40 "$LOG" >&2 || true
    exit 1
  fi
}

cmd_stop() {
  if ! is_running; then echo "not running"; rm -f "$PIDFILE"; exit 0; fi
  local pid; pid="$(cat "$PIDFILE")"
  kill "$pid" 2>/dev/null || true
  for _ in $(seq 1 20); do kill -0 "$pid" 2>/dev/null || break; sleep 0.3; done
  kill -9 "$pid" 2>/dev/null || true
  rm -f "$PIDFILE"
  echo "stopped pid=$pid"
}

cmd_status() {
  if is_running; then echo "running pid=$(cat "$PIDFILE") interval=${INTERVAL}s"; else echo "not running"; fi
  if [[ -f "$DIR/tg_push_fast_state.json" ]]; then
    "$PYTHON" -c "import json; d=json.load(open('$DIR/tg_push_fast_state.json')); print('last', d.get('at'), 'new', d.get('new_message_ids'), 'added', d.get('added'), 'elapsed', d.get('elapsed_s'))"
  fi
}

cmd_restart() { cmd_stop || true; cmd_start; }
cmd_ensure() { if is_running; then echo "ok pid=$(cat "$PIDFILE")"; exit 0; fi; cmd_start; }
cmd_once() {
  "$PYTHON" "$PY" --limit "$LIMIT" "$@"
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  ensure) cmd_ensure ;;
  once) shift; cmd_once "$@" ;;
  *) echo "usage: $0 start|stop|restart|status|ensure|once [--force|--offline|--no-publish]"; exit 2 ;;
esac
