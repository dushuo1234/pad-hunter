#!/usr/bin/env bash
# Start / stop / status for 工作台即将开始高频提醒 (workbench_soon_watch).
set -euo pipefail
DIR=/workspace/project-monitor
mkdir -p "$DIR/alerts/x_inbox/done"
PIDFILE="$DIR/workbench_soon_watch.pid"
LOG="$DIR/alerts/workbench_soon_watch.log"
PY="$DIR/workbench_soon_watch.py"
TICK="${WB_SOON_TICK:-5}"

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
    if tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "workbench_soon_watch.py"; then
      return 0
    fi
  fi
  return 1
}

cmd_start() {
  if is_running; then
    echo "already running pid=$(cat "$PIDFILE") tick=${TICK}s log=$LOG"
    exit 0
  fi
  # stale pidfile
  rm -f "$PIDFILE"
  nohup python3 "$PY" --daemon --tick "$TICK" >>"$LOG" 2>&1 &
  echo $! >"$PIDFILE"
  sleep 0.4
  if is_running; then
    echo "started pid=$(cat "$PIDFILE") tick=${TICK}s log=$LOG"
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

cmd_ensure() { if is_running; then echo "ok pid=$(cat "$PIDFILE")"; exit 0; fi; cmd_start; }

# 守护：每 30s 检查一次，挂了就拉起（自身 pid 写在 workbench_soon_watchdog.pid）
cmd_watchdog() {
  echo $$ > "$DIR/workbench_soon_watchdog.pid"
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
    if [[ -f "$DIR/workbench_soon_watchdog.pid" ]] && kill -0 "$(cat "$DIR/workbench_soon_watchdog.pid")" 2>/dev/null; then
      echo "watchdog already running pid=$(cat "$DIR/workbench_soon_watchdog.pid")"; exit 0; fi
    nohup bash "$0" _watchdog >/dev/null 2>&1 &
    sleep 0.5; echo "watchdog started pid=$(cat "$DIR/workbench_soon_watchdog.pid")" ;;
  *)
    echo "Usage: $0 {start|stop|restart|status|ensure|watchdog}"
    echo "Env: WB_SOON_TICK=5 WB_SOON_SITE_EVERY=45 WB_SOON_X_EVERY=60"
    exit 1
    ;;
esac
