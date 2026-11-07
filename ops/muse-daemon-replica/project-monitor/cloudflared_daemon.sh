#!/usr/bin/env bash
# Cloudflare named tunnel "pad-hunter" -> https://api.adualpha.win (remotely-managed ingress).
# Dashboard route: api.adualpha.win -> http://127.0.0.1:8787 ; cf_port_forward.py forwards 8787 -> 8780 (workbench API).
# Usage: cloudflared_daemon.sh start|stop|restart|status
# Token is read from .secrets/cloudflare_tunnel_token_raw.txt into env (never on the command line / logs).
set -uo pipefail
DIR=/workspace/project-monitor
cd "$DIR"
CF=/usr/local/bin/cloudflared; [[ -x "$CF" ]] || CF="$DIR/bin/cloudflared"
PY="$DIR/.venv/bin/python"; [[ -x "$PY" ]] || PY=python3
LOOP_PID="$DIR/cloudflared_loop.pid"; CF_PID="$DIR/cloudflared.pid"; LOG="$DIR/cloudflared.log"
FWD_LOOP_PID="$DIR/cf_forward_loop.pid"; FWD_PID="$DIR/cf_forward.pid"; FWD_LOG="$DIR/cf_forward.log"
ts() { TZ=Asia/Shanghai date '+%Y-%m-%d %H:%M:%S Asia/Shanghai'; }
alive() { [[ -f "$1" ]] && kill -0 "$(tr -d ' \n' < "$1")" 2>/dev/null; }

cf_loop() {
  /home/box/.local/bin/fix-argotunnel-hosts >/dev/null 2>&1 || true
  while true; do
    TUNNEL_TOKEN="$(tr -d ' \n\r' < "$DIR/.secrets/cloudflare_tunnel_token_raw.txt")" \
      "$CF" tunnel --no-autoupdate --protocol "${CF_PROTOCOL:-http2}" run >>"$LOG" 2>&1 < /dev/null &
    echo $! > "$CF_PID"
    echo "[$(ts)] cloudflared started pid=$(cat "$CF_PID")" >> "$LOG"
    wait "$(cat "$CF_PID")"
    echo "[$(ts)] cloudflared exited rc=$? ; restarting in 5s" >> "$LOG"
    sleep 5
  done
}
fwd_loop() {
  while true; do
    "$PY" "$DIR/cf_port_forward.py" >>"$FWD_LOG" 2>&1 < /dev/null &
    echo $! > "$FWD_PID"; echo "[$(ts)] forwarder started pid=$(cat "$FWD_PID")" >> "$FWD_LOG"
    wait "$(cat "$FWD_PID")"; echo "[$(ts)] forwarder exited rc=$? ; restarting in 2s" >> "$FWD_LOG"; sleep 2
  done
}
stop_one() { if alive "$1"; then kill "$(cat "$1")" 2>/dev/null; sleep 0.5; kill -9 "$(cat "$1")" 2>/dev/null; fi; rm -f "$1"; }

case "${1:-}" in
  start)
    alive "$FWD_LOOP_PID" || { setsid nohup bash "$0" _fwd_loop >/dev/null 2>&1 < /dev/null & echo $! > "$FWD_LOOP_PID"; }
    alive "$LOOP_PID" || { setsid nohup bash "$0" _cf_loop >/dev/null 2>&1 < /dev/null & echo $! > "$LOOP_PID"; }
    sleep 1; bash "$0" status ;;
  _cf_loop) cf_loop ;;
  _fwd_loop) fwd_loop ;;
  ensure) alive "$LOOP_PID" && alive "$FWD_LOOP_PID" || bash "$0" start ;;
  stop) stop_one "$LOOP_PID"; stop_one "$CF_PID"; stop_one "$FWD_LOOP_PID"; stop_one "$FWD_PID"; echo stopped ;;
  restart) bash "$0" stop; bash "$0" start ;;
  status)
    alive "$LOOP_PID" && echo "cloudflared loop: pid=$(cat "$LOOP_PID") cloudflared pid=$(cat "$CF_PID" 2>/dev/null)" || echo "cloudflared: not running"
    alive "$FWD_LOOP_PID" && echo "forwarder loop: pid=$(cat "$FWD_LOOP_PID") forwarder pid=$(cat "$FWD_PID" 2>/dev/null) 127.0.0.1:8787->8780" || echo "forwarder: not running" ;;
  *) echo "Usage: $0 {start|stop|restart|status|ensure}"; exit 1 ;;
esac
