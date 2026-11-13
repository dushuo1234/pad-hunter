#!/usr/bin/env bash
# Light health check + auto-heal for workbench_soon_watch (+ watchdog).
# Quiet on healthy; prints one line and exits 0 after heal / 1 on hard fail.
set -euo pipefail
DIR=/workspace/project-monitor
DAEMON="$DIR/workbench_soon_watch_daemon.sh"
PIDFILE="$DIR/workbench_soon_watch.pid"
WD_PIDFILE="$DIR/workbench_soon_watchdog.pid"
STATE="$DIR/alerts/workbench_soon_state.json"
LOG="$DIR/alerts/workbench_soon_watch.log"
# If last_cycle / state mtime older than this → treat as stale (seconds)
STALE_SECS="${WB_SOON_STALE_SECS:-180}"
COOLDOWN_SECS="${WB_SOON_HEAL_COOLDOWN:-120}"
REPORT_FILE="$DIR/alerts/workbench_soon_health.last"
LOCK="$DIR/alerts/workbench_soon_health.lock"
COOLDOWN_FILE="$DIR/alerts/workbench_soon_health.cooldown"

cd "$DIR"
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "skip locked"
  exit 0
fi

alive_cmd() {
  local pidfile="$1" needle="$2"
  [[ -f "$pidfile" ]] || return 1
  local pid
  pid="$(tr -d ' \n' < "$pidfile")"
  [[ -n "$pid" ]] || return 1
  kill -0 "$pid" 2>/dev/null || return 1
  tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | grep -q "$needle"
}

soon_ok=0
wd_ok=0
stale=0
actions=()

if alive_cmd "$PIDFILE" "workbench_soon_watch.py"; then
  soon_ok=1
else
  actions+=("start_soon")
fi

if alive_cmd "$WD_PIDFILE" "_watchdog"; then
  wd_ok=1
else
  # also accept cmdline with workbench_soon_watch_daemon.sh _watchdog
  if [[ -f "$WD_PIDFILE" ]]; then
    local_pid="$(tr -d ' \n' < "$WD_PIDFILE" 2>/dev/null || true)"
    if [[ -n "${local_pid:-}" ]] && kill -0 "$local_pid" 2>/dev/null; then
      if tr '\0' ' ' < "/proc/$local_pid/cmdline" 2>/dev/null | grep -qE "workbench_soon_watch_daemon|_watchdog"; then
        wd_ok=1
      fi
    fi
  fi
  if [[ "$wd_ok" -eq 0 ]]; then
    actions+=("start_watchdog")
  fi
fi

# Freshness: prefer python --status last_cycle.at, else state/log mtime
now_epoch=$(date +%s)
fresh_age=""
if [[ "$soon_ok" -eq 1 ]]; then
  last_at=$(python3 "$DIR/workbench_soon_watch.py" --status 2>/dev/null | python3 -c '
import sys,json,re
from datetime import datetime
raw=sys.stdin.read()
# status prints a line then JSON
m=re.search(r"\{[\s\S]*\}\s*$", raw)
if not m:
  print(""); raise SystemExit
d=json.loads(m.group(0))
at=(d.get("last_cycle") or {}).get("at") or (d.get("pins") or {}).get("at") or ""
print(at)
' 2>/dev/null || true)
  if [[ -n "${last_at:-}" ]]; then
    last_epoch=$(python3 -c '
from datetime import datetime
import sys
s=sys.argv[1].strip()
# 2026-10-28T14:07:31+08:00
print(int(datetime.fromisoformat(s).timestamp()))
' "$last_at" 2>/dev/null || echo "")
    if [[ -n "${last_epoch:-}" ]]; then
      fresh_age=$((now_epoch - last_epoch))
      if [[ "$fresh_age" -gt "$STALE_SECS" ]]; then
        stale=1
        actions+=("restart_stale")
      fi
    fi
  elif [[ -f "$STATE" ]]; then
    mtime=$(stat -c %Y "$STATE" 2>/dev/null || echo 0)
    fresh_age=$((now_epoch - mtime))
    if [[ "$fresh_age" -gt "$STALE_SECS" ]]; then
      stale=1
      actions+=("restart_stale")
    fi
  fi
fi

healed=0
# cooldown: avoid restart storms from overlapping health+watchdog
if [[ ${#actions[@]} -gt 0 ]] && [[ -f "$COOLDOWN_FILE" ]]; then
  last_heal=$(tr -d " \n" < "$COOLDOWN_FILE" || echo 0)
  if [[ "$last_heal" =~ ^[0-9]+$ ]] && (( now_epoch - last_heal < COOLDOWN_SECS )); then
    echo "cooldown soon=$soon_ok wd=$wd_ok stale=$stale age=${fresh_age:-?}s actions=${actions[*]} left=$((COOLDOWN_SECS - (now_epoch - last_heal)))s" | tee "$REPORT_FILE"
    exit 0
  fi
fi
if [[ ${#actions[@]} -gt 0 ]]; then
  for a in "${actions[@]}"; do
    case "$a" in
      start_soon)
        bash "$DAEMON" start >/dev/null
        healed=1
        ;;
      start_watchdog)
        bash "$DAEMON" watchdog >/dev/null
        healed=1
        ;;
      restart_stale)
        # only restart if process still "alive" but stale
        bash "$DAEMON" restart >/dev/null || bash "$DAEMON" start >/dev/null
        bash "$DAEMON" watchdog >/dev/null || true
        healed=1
        ;;
    esac
  done
  date +%s > "$COOLDOWN_FILE"
  # re-check
  soon_ok=0; wd_ok=0
  alive_cmd "$PIDFILE" "workbench_soon_watch.py" && soon_ok=1 || true
  if alive_cmd "$WD_PIDFILE" "_watchdog" || { [[ -f "$WD_PIDFILE" ]] && kill -0 "$(cat "$WD_PIDFILE")" 2>/dev/null && tr '\0' ' ' <"/proc/$(cat "$WD_PIDFILE")/cmdline" 2>/dev/null | grep -qE "workbench_soon_watch_daemon|_watchdog"; }; then
    wd_ok=1
  fi
fi

sp=$(tr -d ' \n' < "$PIDFILE" 2>/dev/null || echo -)
wp=$(tr -d ' \n' < "$WD_PIDFILE" 2>/dev/null || echo -)
line="soon=$soon_ok pid=$sp wd=$wd_ok wdpid=$wp stale=$stale age=${fresh_age:-?}s actions=${actions[*]:-none} healed=$healed"

# Only write/report when healed or unhealthy after attempt
if [[ "$healed" -eq 1 ]] || [[ "$soon_ok" -eq 0 ]] || [[ "$wd_ok" -eq 0 ]]; then
  echo "$line" | tee "$REPORT_FILE"
  [[ "$soon_ok" -eq 1 && "$wd_ok" -eq 1 ]] && exit 0 || exit 1
fi
# healthy quiet — still refresh last healthy marker lightly
echo "ok $line" > "$REPORT_FILE"
exit 0
