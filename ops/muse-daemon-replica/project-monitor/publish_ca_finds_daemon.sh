#!/usr/bin/env bash
# Backup watcher: publish ca_finds.json when mtime changes (onchain_lock also publishes inline).
set -euo pipefail
DIR=/workspace/project-monitor
PIDFILE="$DIR/publish_ca_finds_watch.pid"
LOG="$DIR/publish_ca_finds_watch.log"
PYTHON="$DIR/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
INTERVAL="${PUBLISH_CA_INTERVAL:-3}"

cd "$DIR"
is_running() {
  [[ -f "$PIDFILE" ]] || return 1
  local pid; pid="$(tr -d ' \n' < "$PIDFILE")"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "publish_ca_finds_pages.py" || return 1
  return 0
}
case "${1:-}" in
  start)
    if is_running; then echo "already running pid=$(cat "$PIDFILE")"; exit 0; fi
    nohup "$PYTHON" "$DIR/publish_ca_finds_pages.py" --watch --interval "$INTERVAL" >>"$LOG" 2>&1 &
    echo $! >"$PIDFILE"
    sleep 0.4
    if is_running; then echo "started pid=$(cat "$PIDFILE") log=$LOG"; else echo "failed"; tail -20 "$LOG"; exit 1; fi
    ;;
  stop)
    if ! is_running; then rm -f "$PIDFILE"; echo "not running"; exit 0; fi
    kill "$(cat "$PIDFILE")" 2>/dev/null || true
    rm -f "$PIDFILE"; echo stopped
    ;;
  status)
    if is_running; then echo "running pid=$(cat "$PIDFILE")"; else echo "not running"; fi
    ;;
  ensure)
    if is_running; then echo "ok pid=$(cat "$PIDFILE")"; else "$0" start; fi
    ;;
  *) echo "Usage: $0 {start|stop|status|ensure}"; exit 1 ;;
esac
