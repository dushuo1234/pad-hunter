# 今日项目清单 · 部署者猎取（代币 CA）

adu 2026-10-28：针对 **今日项目清单** 不定时拉取部署者 / 关联钱包 / 工厂部署信息，尽量在 `listing_at` 前钉住 **代币 CA**（非 NFT）。有些团队会提前部署好代币。

## What
对 `today_projects.json` 每个 handle：
1. 汇总钱包：`wallet_watchlist.json`、`watched_wallets.json`、`ca_finds`（kind=wallet / traced_from）
2. 已知合约（`ca_finds` / `watchlist.ca` / 官网扫到的合约）→ `getcontractcreation` 解析 creator，写入监控钱包（medium）
3. 有官网则轻量抓 `0x`（钱包进猎取；`ca_gate.is_token` 的进钉住路径）
4. 对钱包跑 `trace_wallet_ca`（CREATE / CREATE2 / launchpad factory；T-20 窗内 `force_recent`）
5. **仅** `ca_gate.verify_address(...).is_token` 才算钉住：
   - `alerts/today_deployer_hunt_alerts.jsonl` + workbench alert
   - `_today_deployer_hunt_msg.txt`（给 parent / 扫描）
   - 可选 rebuild `ca_finds.json`
   - sniper **dry_run**（不实买）
   - **不直推电报**（归 DeepSeek/扫描；应急 `TODAY_TG_BY_HUNT=1`）

## Frequency（Asia/Shanghai，按最近 listing_at）
| 距开盘 | 间隔（可环境变量覆盖） |
|--------|------------------------|
| >2h 或默认 | `TODAY_DEPLOYER_FAR=600`（10min） |
| ≤2h | `TODAY_DEPLOYER_NEAR=180`（3min） |
| ≤20min（T-20） | `TODAY_DEPLOYER_T20=60`（60s） |
| 无 listing_at | `TODAY_DEPLOYER_NOTIME=900`（15min） |

## Daemon
```bash
bash /workspace/project-monitor/today_deployer_hunt_daemon.sh ensure|status|stop|watchdog
python3 /workspace/project-monitor/today_deployer_hunt.py once|watch|status
```
Hooked from `today_projects_tick.sh` via `ensure` + `watchdog`.

## Rules
- 只覆盖今日清单 handles；NFT / hybrid_404 忽略
- 绝不编造 listing_at / CA
- 电报 CA 仍走扫描闸（今日清单 + 高置信/官推）
- Sniper 保持 `dry_run=true`
- **固定CA**（`ca_confidence.is_ca_fixed`）：官推 **或** 部署者/关联钱包部署 → 才 dry_fire / 可进电报应急闸；纯站点刮取代币仍写 workbench 为待确认

## Files
- `today_deployer_hunt.py` / `today_deployer_hunt_daemon.sh`
- state: `alerts/today_deployer_hunt_state.json`
- status: `alerts/today_deployer_hunt_status.json`
- creator cache: `alerts/today_deployer_creator_cache.json`
- log: `alerts/today_deployer_hunt.log`

## Blockers / gaps
- **Robinhood / BSC creator**：Etherscan V2 free plan 不覆盖 chainid=4663/56；RH Blockscout CF 拦截 → `getcontractcreation` 常 miss。已有代币仍可经 `ca_gate` 钉住；部署者钱包要等付费档、官推，或其它链上线索。
- **无官网 / 无已扫地址** 的清单项（如当前 hoodora_rh、bStonkAgents 钱包=0）：本环无法凭空造钱包，依赖 T-20/官推/官网恢复后再猎。
- 电报不直推；扫描侧读 `_today_deployer_hunt_msg.txt` / workbench。
