# 今日项目清单 · T-20 高频 CA

## What
For each item in `today_projects.json` whose `listing_at` is within the next **20 minutes**:
- 6551 Twitter: prefer WSS (`watch_add` + subscribe); REST `user_tweets` every ~5s as fallback
- Existing CA pipelines: read `ca_finds.json` every cycle; `today_projects_boost.json` marks T-20 handles so `workbench_soon_watch` scans site every **~5s** (today list otherwise ~15s)
- High-confidence CA → workbench alert (`kind=ca|today_t20|x_post`, `t20=true`) + `alerts/today_t20_alerts.jsonl` + `_today_t20_highconf_msg.txt` + dry `fire_buy`
- Official X CA → `mark_launched_from_ca.force_launch` → 已开盘, drop from today list, `_today_t20_launched_msg.txt`, stop watching that handle

## Daemon
```bash
bash /workspace/project-monitor/today_t20_watch_daemon.sh ensure|status|stop|watchdog
python3 /workspace/project-monitor/today_t20_watch.py status|once|watch
```
Hooked from `today_projects_tick.sh` via `ensure`.

## Sniper
`sniper_config.json` **dry_run=true** — never live-buys from this path.

## Schedule (current 3, Asia/Shanghai)
| Project | listing_at | T-20 starts |
|---------|------------|-------------|
| Stonk Agents @bStonkAgents | 2026-10-28 23:00 | **22:40** |
| hoodora @hoodora_rh | 2026-10-29 01:00 | **00:40** |
| Fishesrh @Fishesrh | 2026-10-29 01:00 | **00:40** |

## Official-account gate (2026-10-29, Capta incident)
A tweet only yields 固定CA / 已开盘 when ALL hold (else it is a low, non-pushed candidate `x_post`):
- handle is a project official account — `ca_confidence.non_project_account()` (non_project_handles.json, personal bio like "Founder @X", or 个人号/KOL card risk not contradicted by a project bio)
- CA is in the author's own text (not only in a quote / retweet)
- CA not in `ca_denylist.json` (also enforced in is_ca_fixed, record_lock, push_ca, sniper fire_buy, today_ca_push)
- verified token symbol/name matches project name/handle or a $TICKER in the tweet (unknown symbol → allowed, keeps speed)
KOL handles are also excluded from today_projects (today_projects_sync.is_launched). 青年大学习 "推送时间" is no longer parsed as listing time.
