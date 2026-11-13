#!/usr/bin/env bash
# Local wrangler for pad-hunter-workbench on 127.0.0.1:43117 (adualpha.win tunnel target).
set -uo pipefail
DIR=/workspace/project-monitor/cf-workbench
LOG=/workspace/project-monitor/cf_workbench_dev.log
PIDF=/workspace/project-monitor/cf_workbench_dev.pid
LOOP=/workspace/project-monitor/cf_workbench_dev_loop.pid
cd "$DIR"
alive() { [[ -f "$1" ]] && kill -0 "$(tr -d ' \n' < "$1")" 2>/dev/null; }
case "${1:-}" in
  start|_loop)
    if [[ "${1}" == "start" ]]; then
      alive "$LOOP" && { echo already; exit 0; }
      setsid nohup bash "$0" _loop >/dev/null 2>&1 < /dev/null &
      echo $! > "$LOOP"
      sleep 2
      bash "$0" status
      exit 0
    fi
    while true; do
      npx wrangler dev --ip 127.0.0.1 --port 43117 --show-interactive-dev-session false >>"$LOG" 2>&1 < /dev/null &
      echo $! > "$PIDF"
      echo "[$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S Asia/Shanghai')] wrangler started pid=$(cat "$PIDF")" >> "$LOG"
      wait "$(cat "$PIDF")"
      echo "[$(TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S Asia/Shanghai')] wrangler exited rc=$? ; restart in 3s" >> "$LOG"
      sleep 3
    done
    ;;
  stop)
    if alive "$LOOP"; then kill "$(cat "$LOOP")" 2>/dev/null; fi
    if alive "$PIDF"; then kill "$(cat "$PIDF")" 2>/dev/null; sleep 1; kill -9 "$(cat "$PIDF")" 2>/dev/null; fi
    # also kill any wrangler/workerd on 43117
    pkill -f 'wrangler dev --ip 127.0.0.1 --port 43117' 2>/dev/null || true
    rm -f "$LOOP" "$PIDF"
    echo stopped
    ;;
  status)
    alive "$LOOP" && echo "loop pid=$(cat "$LOOP")" || echo "loop: not running"
    alive "$PIDF" && echo "wrangler pid=$(cat "$PIDF")" || echo "wrangler: not running"
    ss -tlnp 2>/dev/null | grep 43117 || true
    ;;
  *) echo "Usage: $0 {start|stop|status}"; exit 1 ;;
esac
