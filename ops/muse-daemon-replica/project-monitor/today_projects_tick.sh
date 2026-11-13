#!/usr/bin/env bash
# 今日项目清单轻量 tick：sync → playbook 刷新(仅过期) → 2h 提醒 → T-20 ensure → 可选 publish
# 供 parent 例程调度；勿在此重写 ca-2。
set -euo pipefail
DIR=/workspace/project-monitor
cd "$DIR"
PUBLISH="${TODAY_PUBLISH:-1}"

SYNC_ARGS=()
PB_ARGS=()
if [[ "$PUBLISH" == "1" || "$PUBLISH" == "true" || "$PUBLISH" == "yes" ]]; then
  SYNC_ARGS+=(--publish)
  PB_ARGS+=(--publish)
fi

python3 "$DIR/today_projects_sync.py" "${SYNC_ARGS[@]}" || true
# playbook：不 force；已有 6h 内 playbook 会跳过（保留人工/DeepSeek 写入）
python3 "$DIR/today_projects_playbook.py" "${PB_ARGS[@]}" || true
python3 "$DIR/today_projects_remind.py" || true
# 今日清单 CA API → api.adualpha.win（本地机器人拉取）
python3 "$DIR/today_ca_push.py" sync || true
# 电报推送归 DeepSeek/扫描（勿在本 tick 直推）。脚本仍可用：today_projects_tg_push.py / telegram_today_only.py
# TODAY_TG_BY_TICK=1 仅应急回退
if [[ "${TODAY_TG_BY_TICK:-0}" == "1" ]]; then
  if [[ "${TODAY_TG_FORCE:-0}" == "1" ]]; then
    python3 "$DIR/today_projects_tg_push.py" --force || true
  else
    python3 "$DIR/today_projects_tg_push.py" || true
  fi
fi

# T-20 高频 CA（开盘前 20 分钟）：ensure daemon；空窗也保持进程以便准时进入
bash "$DIR/today_t20_watch_daemon.sh" ensure || true
python3 "$DIR/today_t20_watch.py" status 2>/dev/null | head -c 2000 || true

# 今日清单部署者猎取（钉住代币 CA）：ensure + watchdog
bash "$DIR/today_deployer_hunt_daemon.sh" ensure || true
bash "$DIR/today_deployer_hunt_daemon.sh" watchdog || true
python3 "$DIR/today_deployer_hunt.py" status 2>/dev/null | head -c 2000 || true

if [[ -s "$DIR/_today_remind_msg.txt" ]]; then
  echo "[today_tick] remind pending → $DIR/_today_remind_msg.txt"
else
  echo "[today_tick] no remind"
fi
if [[ -s "$DIR/_today_t20_highconf_msg.txt" ]]; then
  echo "[today_tick] T-20 highconf pending → $DIR/_today_t20_highconf_msg.txt"
fi
if [[ -s "$DIR/_today_t20_launched_msg.txt" ]]; then
  echo "[today_tick] T-20 launched pending → $DIR/_today_t20_launched_msg.txt"
fi
if [[ -s "$DIR/_today_deployer_hunt_msg.txt" ]]; then
  echo "[today_tick] deployer-hunt token pending → $DIR/_today_deployer_hunt_msg.txt"
fi

