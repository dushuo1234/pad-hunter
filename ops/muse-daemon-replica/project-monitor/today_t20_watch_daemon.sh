#!/usr/bin/env bash
# Start / stop / status / ensure for 今日项目清单 T-20 高频 CA (today_t20_watch).
set -euo pipefail
DIR=/workspace/project-monitor
mkdir -p "$DIR/alerts"
PIDFILE="$DIR/today_t20_watch.pid"
LOG="$DIR/alerts/today_t20_watch.log"
PY="$DIR/today_t20_watch.py"
# Prefer venv (websockets for 6551 WSS)
if [[ -x "$DIR/.venv/bin/python" ]]; then
  PYTHON="$DIR/.venv/bin/python"
else
  PYTHON=python3
fi

cd "$DIR"
if [[ -f "$DIR/today_ca_speed.env" ]]; then
  # shellcheck disable=SC1091
  source "$DIR/today_ca_speed.env"
fi

is_running() {
  if [[ ! -f "$PIDFILE" ]]; then
    return 1
  fi
  local pid
  pid="$(tr -d ' \n' < "$PIDFILE")"
  [[ -n "$pid" ]] || return 1
  if kill -0 "$pid" 2>/dev/null; then
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "today_t20_watch.py"; then
      return 0
    fi
  fi
  return 1
}

cmd_start() {
  if is_running; then
    echo "already running pid=$(cat "$PIDFILE") log=$LOG"
    exit 0
  fi
  rm -f "$PIDFILE"
  nohup "$PYTHON" "$PY" watch >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.5
  if is_running; then
    echo "started pid=$(cat "$PIDFILE") python=$PYTHON log=$LOG"
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
  "$PYTHON" "$PY" status || true
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

cmd_watchdog() {
  echo $$ > "$DIR/today_t20_watchdog.pid"
  while true; do
    if ! is_running; then
      echo "[$(date '+%F %T')] watchdog: restarting" >>"$LOG"
      ( cmd_start ) >>"$LOG" 2>&1 || true
    fi
    sleep 30
  done
}

case "${1:-}" in
  start) cmd_start ;;
  stop) cmd_stop ;;
  restart) cmd_restart ;;
  status) cmd_status ;;
  ensure) cmd_ensure ;;
  _watchdog) cmd_watchdog ;;
  watchdog)
    if [[ -f "$DIR/today_t20_watchdog.pid" ]] && kill -0 "$(cat "$DIR/today_t20_watchdog.pid")" 2>/dev/null; then
      echo "watchdog already running pid=$(cat "$DIR/today_t20_watchdog.pid")"; exit 0
    fi
    nohup bash "$0" _watchdog >/dev/null 2>&1 &
    sleep 0.5
    echo "watchdog started pid=$(cat "$DIR/today_t20_watchdog.pid")"
    ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|ensure|watchdog}"
    echo "Env: TODAY_T20_MINUTES=20 TODAY_T20_TICK=3 TODAY_T20_REST_EVERY=5 TODAY_T20_SITE_EVERY=5"
    exit 1
    ;;
esac
