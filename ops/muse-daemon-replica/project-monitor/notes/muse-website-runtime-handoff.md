# Pad Hunter 网站/工作台运行交接（给 Muse）

> **读者**：Meta Muse / Muse AI（接手网站与工作台运行）  
> **作者侧**：Ori / box 运维交接  
> **时区**：Asia/Shanghai（UTC+8）  
> **仓库**：`dushuo1234/pad-hunter`（GitHub Pages 前端）  
> **本机根目录**：`/workspace/project-monitor`  
> **禁止**：本文档与任何聊天中粘贴 API token、GitHub token、隧道 token、钱包私钥；鉴权只写**路径与请求头名**。

---

## 1. 系统概览（网站 / 工作台 / API / 本机守护 / 例行）

Pad Hunter 是「项目推送 + 即将开盘 + CA 早期发现」看板，由三层组成：

| 层 | 是什么 | 谁跑 |
|---|---|---|
| **前端站点** | GitHub Pages 上的 `pad-hunter`（`https://dushuo1234.github.io/pad-hunter/` 一类入口；CORS 白名单含 `https://dushuo1234.github.io`） | 静态托管；数据靠 Contents API / PR 更新 |
| **云端工作台 API** | Cloudflare Worker + Durable Object，公网 `https://api.adualpha.win`，room `pad-hunter-v6`（VERSION 约 `1.8.0-cf`） | Cloudflare；源码在 `/workspace/project-monitor/cf-workbench/` |
| **本机（box）** | 雷达采集、官网秒级轮询、链上锁、TG 近实时同步、本地 FastAPI 兜底 `127.0.0.1:8780`、发布到 Pages | `/workspace/project-monitor/*_daemon.sh` + Cursor 例行 |

**职责分工（边界）**（2026-11-04 adu 裁定：公网侧 **与 box 守护** 都交 Muse）

- **Muse（全权网站/运维）**：
  - 公网：API health、Pages 数据时间戳、站点可用性、前端 PR/部署
  - **box**：`/workspace/project-monitor` 下各 `*_daemon.sh` 的 ensure/start/stop/status、看 pid/日志、`.site_scan_paused` 暂停/恢复、本地 8780 健康、发布脚本
- **Ori（及其他）**：监控策略、CA 闸门调参、买卖/狙击、项目钱包签名、Cursor 例行业务判断；**不再默认管守护起停**（过渡期可应 Muse 请求代执行一次 ensure）。
- **硬边界**：项目钱包 **server-only**——运维机 **不登录、不签名**钱包；`sniper_config.json` 路径上 `dry_run=true`，本路径不实买。勿越权。

**接入缺口（必须解决才能真正接手 box）**

当前守护跑在 **Cursor Grok Bot 共享 box**（路径 `/workspace/project-monitor`）。Meta Muse **默认进不了**这台机。交接文档里的 ensure/pid/日志命令在 Muse 获得等价 shell 之前无法由 Muse 直接执行。可选落地方式（由 adu 开权限，勿把 token 写进仓库）：

1. 给 Muse 一台可 SSH 的运维机，并把 `project-monitor`（含 venv/守护脚本，密钥走 Muse 保险柜不进 git）同步过去，改文档根路径后切流量；或  
2. 在 Muse 可控环境复刻同一套守护；或  
3. 过渡期：Muse 盯公网，需要 ensure 时通过 GitHub issue / 聊天点名 Ori 代跑。

未解决接入前：**所有权归 Muse，执行权仍可能短时落在 Ori**——以 adu 最新口令为准。

**例行（名称 only，喂站点数据；调度在 Cursor Routines，不是本机 cron）**

1. 项目推送监控  
2. 项目官网探活  
3. 开盘与CA预警  
4. 官网秒级CA快报  
5. 工作台官推高频刷新  
6. 今日项目清单  

例行负责周期性拉 X/TG、跑 `run_listing_onchain_js.sh` 一类批处理；本机守护负责秒级/分钟级常驻。

---

## 2. 关键路径与入口 URL

### 2.1 URL

| 用途 | URL / 路径 |
|---|---|
| 云端工作台 API | `https://api.adualpha.win` |
| 健康检查（公开） | `GET https://api.adualpha.win/health` |
| WebSocket | `wss://api.adualpha.win/v1/workbench/ws?token=…`（token 用查询参数；HTTP 用头） |
| Workers.dev 兜底 | `https://pad-hunter-workbench.a18675489863.workers.dev` |
| 本机工作台 API | `http://127.0.0.1:8780`（`workbench_api.py`） |
| 本机 health | `GET http://127.0.0.1:8780/health` |
| 前端 Pages | 仓库 `dushuo1234/pad-hunter` → GitHub Pages（CORS 允许 `dushuo1234.github.io`） |
| 本地雷达看板（调试） | `/workspace/push-radar/` → `python3 -m http.server 8765` → `http://127.0.0.1:8765/` |

### 2.2 本机关键目录

```
/workspace/project-monitor/          # 运维与守护主目录
  cf-workbench/                      # Cloudflare Worker 源码 + deploy.sh
  workbench_api.py                   # 本地 FastAPI（8780）
  workbench_api_token.txt            # 鉴权 token 文件（chmod 600；勿提交、勿粘贴）
  workbench_active.json              # 工作台 pins 本地镜像
  workbench_reviewed.json
  ca_finds.json                      # CA 汇总
  watchlist.json
  .site_scan_paused                  # 存在即表示「扫描暂停」运维标记（见 §6）
  *_daemon.sh                        # 各守护起停脚本
  .secrets/github_token              # Pages 发布用 GH token（勿打印）
  alerts/                            # 各守护日志与状态
/workspace/push-radar/data/          # candidates.json / projects.json / launched.json / ca_finds.json 本地镜像
/workspace/publish-pages-data/       # 发布缓冲镜像（若存在）
/home/box/.tg-monitor/               # TG sync_site.py + Telethon
```

### 2.3 前端仓库

- GitHub：`https://github.com/dushuo1234/pad-hunter`
- 数据文件目标（main）：`public/data/candidates.json`、`projects.json`、`launched.json`、`ca_finds.json` 等  
- 直播分支双写：`gh-pages` 上 `data/<同名>`（避免 Vite orphan / cancel-in-progress 导致 CDN 滞后）
- 发布脚本：`publish_pages_file.py`、`publish_ca_finds_pages.py`（Contents API，不 echo token）

---

## 3. 本机如何启动 / 停止 / ensure 各守护（命令清单）

统一约定：在 box 上执行；多数脚本支持 `start|stop|restart|status|ensure`。  
**优先用 `ensure`**（已在跑则不动；挂了再拉起）。

```bash
DIR=/workspace/project-monitor
cd "$DIR"

# --- 工作台本地 API（8780）+ watchdog；公网隧道默认 provider=none（站点已走 CF Worker）---
bash workbench_api_daemon.sh ensure|status|stop|restart|url

# --- 工作台「即将开始」高频提醒（默认 tick 5s）---
bash workbench_soon_watch_daemon.sh ensure|status|stop|restart|watchdog
# 环境：WB_SOON_TICK=5

# --- 官网秒级轮询（默认 1s；工作台非空时只扫工作台站点）---
bash fast_site_poll_daemon.sh start|stop|restart|status
# 注意：此脚本 Usage 无 ensure；用 start 幂等（已跑则提示 already running）
# FAST_SITE_INTERVAL=1

# --- TG → candidates 近实时（默认 60s）---
bash tg_push_fast_daemon.sh ensure|status|stop|restart
# TG_PUSH_FAST_INTERVAL=60  TG_PUSH_FAST_LIMIT=40
# 单次：bash tg_push_fast_daemon.sh once [--force|--offline|--no-publish]

# --- 开盘时间 / listing 扫描（默认 900s，带 --publish）---
bash listing_scan_daemon.sh start|stop|restart|status|once
# LISTING_SCAN_INTERVAL=900  LISTING_SCAN_WORKERS=12

# --- CA finds 变更 → Pages 备份发布（mtime 轮询，默认 3s）---
bash publish_ca_finds_daemon.sh ensure|status|start|stop

# --- 链上 lock 守护（默认 interval 2s）---
bash onchain_lock_daemon.sh ensure|status|stop|restart
# ONCHAIN_LOCK_INTERVAL=2

# --- TapeOut / TapeRobot 专用 CA 盯梢 ---
bash tapeout_watch_daemon.sh ensure|status|stop|restart
# TAPEOUT_WATCH_INTERVAL=2

# --- 今日清单 T-20 ---
bash today_t20_watch_daemon.sh ensure|status|stop|restart|watchdog

# --- 今日清单部署者猎取 ---
bash today_deployer_hunt_daemon.sh ensure|status|stop|restart|watchdog

# --- 站点「手动确认已开盘」→ 本机 prune + Pages（约 45s）---
bash sync_manual_launched_daemon.sh ensure|status|stop|restart
# SYNC_MANUAL_INTERVAL=45

# --- 可选：本地 wrangler dev（43117）/ 旧 tunnel；生产 API 已是 Worker 路由 ---
bash cf_workbench_dev_daemon.sh start|stop|status
bash cloudflared_daemon.sh ensure|status|stop   # 命名隧道；生产流量优先 Worker route
```

**批量健康（示例）**

```bash
for s in workbench_api_daemon workbench_soon_watch_daemon tg_push_fast_daemon \
         onchain_lock_daemon tapeout_watch_daemon publish_ca_finds_daemon \
         sync_manual_launched_daemon today_t20_watch_daemon today_deployer_hunt_daemon; do
  echo "===== $s ====="
  bash /workspace/project-monitor/${s}.sh status || true
done
bash /workspace/project-monitor/fast_site_poll_daemon.sh status || true
bash /workspace/project-monitor/listing_scan_daemon.sh status || true
curl -fsS http://127.0.0.1:8780/health; echo
curl -fsS https://api.adualpha.win/health; echo
```

**批处理流水线（例行「开盘与CA预警」等会跑；非守护）**

```bash
bash /workspace/project-monitor/run_listing_onchain_js.sh
# 内部大致顺序（见 LISTING_CA_README）：
# scan_listing_ca → extract_listing_times → scan_x_progress → extract_x_ca
# → scan_onchain → scan_js_factory_match → trace_wallet_ca → solana_wallet_mints
# → prune_launched → mark_launched_from_ca → build_ca_finds → merge_site_completion
```

---

## 4. 数据流：TG / X / 链上 → 池子 → publish → Pages / 工作台

```
Telegram「项目推送」
  └─ tg_push_fast（~60s）或例行「项目推送监控」（~30m）
       → Telethon fetch（flock: /home/box/.tg-monitor/tg.fetch.lock）
       → sync_site.py → push-radar/data/projects.json
       → merge_projects_into_candidates.py → candidates.json
       → publish_radar_data()  → GitHub main public/data/* + gh-pages data/*
       → cf_radar_push.py      → POST /v1/radar/push → 开着的浏览器 WS 实时雷达

官网 HTML/JS
  └─ fast_site_poll（~1s，工作台优先）+ 批处理 scan_js_factory_match
       → fast_site_alerts.jsonl（SITE_CHANGE / NEW_JS_CA）
       → build_ca_finds.py → ca_finds.json
       → publish_ca_finds_pages / onchain_lock 内联发布

X 官推
  └─ 例行「工作台官推高频刷新」→ x_inbox → workbench_soon_watch
       → POST /v1/workbench/alert → WS workbench_alert
  └─ scan_x_progress / extract_x_ca → X_CA → ca_finds（须过 ca_gate）

链上
  └─ onchain_lock / tapeout_watch / today_deployer_hunt / scan_onchain
       → alerts + ca_finds；固定 CA 规则见 §9

已开盘 / 拉黑
  └─ prune_launched / mark_launched_from_ca / 站点 POST /v1/launched/mark
       → removed_launched.json + blocklist
       → sync_manual_launched 拉云端 manual marks → 本地 prune → launched.json → Pages
       → cf_workbench_prune 推 blocklist 到 DO

今日清单
  └─ today_projects.json ← 例行「今日项目清单」
       → today_ca_push / T-20 / deployer_hunt → /v1/today/cas（WS today_ca）
```

**站点静态数据 vs 实时**

- **静态**：`candidates.json` 等在 Pages（CDN 曾有约 10min `max-age`；前端应软轮询 + cache bust；雷达也可走 `GET /v1/radar/recent`）。
- **实时**：工作台 pins / reviewed / alerts / launched / radar / today_cas 走 `api.adualpha.win` HTTP + WS。

---

## 5. 工作台 API 鉴权与常用端点

### 5.1 鉴权

- **请求头名**：`X-Pad-Hunter-Token`
- **Token 文件（本机）**：`/workspace/project-monitor/workbench_api_token.txt`  
  （Cloudflare Secret 名：`WORKBENCH_TOKEN`，由 `cf-workbench/deploy.sh` 从同一文件 `wrangler secret put`，**禁止 echo / 禁止写进交接聊天**）
- **CORS**：`https://dushuo1234.github.io` + localhost / 127.0.0.1
- **WS**：`wss://api.adualpha.win/v1/workbench/ws?token=…`；错误关闭码 `4401` = token 不对；构建换代可能 `1012`，客户端应重连

### 5.2 云端端点（Worker / DO，以 README + 源码为准）

| Method | Path | 鉴权 | 说明 |
|--------|------|------|------|
| GET | `/health` | 无 | version、pin count 等 |
| GET | `/v1/workbench/pins` | 是 | `{synced_at,items,removed}` |
| POST | `/v1/workbench/sync` | 是 | LWW merge；别名 `POST /v1/workbench/pins/sync` |
| GET | `/v1/workbench/reviewed` | 是 | |
| POST | `/v1/workbench/reviewed/sync` | 是 | |
| GET/POST | `/v1/workbench/blocklist` | 是 | replace 会 **union** 手动已开盘 marks |
| POST | `/v1/workbench/alert` | 是 | 即将开始等提醒；`dry_run` 前端必须忽略 |
| GET | `/v1/workbench/alerts` | 是 | 最近 200；WS 不通时 60s 轮询 |
| WS | `/v1/workbench/ws` | token 查询参数 | hello：pins/reviewed/radar/blocklist/launched/workbench_alerts/today_cas… |
| POST | `/v1/radar/push`（别名 `/v1/radar/candidates`） | 是 | TG 卡推送到开着的标签页 |
| GET | `/v1/radar/recent` | token **或** 允许的 Origin | 近 200 张雷达卡；完整 candidates 仍在 Pages |
| POST | `/v1/launched/mark` | 是 | 网站「确认已开盘」 |
| POST | `/v1/launched/unmark` | 是 | 撤销手动已开盘 |
| GET | `/v1/launched/recent` | 是 | 给前端过滤 + box sync_manual_launched |
| GET | `/v1/today/cas` | 是 | 今日清单 CA；可 `?since=` |
| POST | `/v1/today/cas/push` | 是 | T-20 / 猎取单事件推送 |

### 5.3 本机 FastAPI 额外端点（8780；雷达/探活仍依赖本机）

除 pins/reviewed/ws/health 外还有（LISTING_CA_README）：

- `GET /v1/workbench/status` — 每站探活状态  
- `POST /v1/workbench/check` `{handle}` — 入队立即深扫  
- `GET /v1/workbench/detail?handle=` — 变更史 / CA  
- `GET /v1/radar/candidates|projects|launched|meta` — 本地无 token 读（`Cache-Control: no-store`）  
- Helius hook：`POST /hooks/helius/solana`（运维一般不动）

调用示例（**勿把真实 token 写进脚本仓库**）：

```bash
TOKEN=$(tr -d ' \n' < /workspace/project-monitor/workbench_api_token.txt)
curl -fsS -H "X-Pad-Hunter-Token: $TOKEN" https://api.adualpha.win/v1/workbench/pins | head
curl -fsS https://api.adualpha.win/health
curl -fsS http://127.0.0.1:8780/health
```

### 5.4 Cloudflare 部署（Muse 可维护）

```bash
cd /workspace/project-monitor/cf-workbench
# 或：bash deploy.sh
npm install
npx wrangler login          # 仅首次
npx wrangler secret put WORKBENCH_TOKEN < /workspace/project-monitor/workbench_api_token.txt
npx wrangler deploy --var "BUILD_ID:$(date +%s)"
```

- `wrangler.toml`：`name=pad-hunter-workbench`，`ROOM_NAME=pad-hunter-v6`，route `api.adualpha.win/*`  
- 重置 DO：控制台清空 DO 存储，或改 `ROOM_NAME` 开新房；空房才吃 `seed-*.json`  
- 从本机刷新 seed：`cp workbench_active.json seed-pins.json` 等后再 deploy（仅空房生效）

---

## 6. 暂停 / 恢复扫描（`.site_scan_paused`）

运维约定文件：

```text
/workspace/project-monitor/.site_scan_paused
```

| 操作 | 做法 |
|---|---|
| **暂停** | `touch /workspace/project-monitor/.site_scan_paused`，并按用户要求 `stop` 相关守护；Cursor 例行侧暂停「项目推送监控 / 项目官网探活 / 开盘与CA预警 / 官网秒级CA快报 / 工作台官推高频刷新 / 今日项目清单」等 |
| **恢复** | 删除该文件：`rm -f /workspace/project-monitor/.site_scan_paused`；例行重新 enable；对各守护执行 `ensure` / `start` |
| **检查** | `test -f /workspace/project-monitor/.site_scan_paused && echo PAUSED || echo RUNNING` |

说明：这是 **box 侧运维标记**（与用户「停掉 / 继续任务」对齐）。恢复后务必再跑一遍 §3 的 status 清单，确认 API health 与关键 pid 正常。部分例行/脚本若检测到该文件应跳过扫描——以当前脚本实现为准；即使用户口头暂停，也以「标记文件 + 守护 stop」双保险。

---

## 7. 发布与前端部署注意

### 7.1 数据发布（box → GitHub）

```bash
# 任意单文件 → main 上 public/data/...
python3 /workspace/project-monitor/publish_pages_file.py \
  /workspace/push-radar/data/candidates.json public/data/candidates.json

# 雷达四件套双写 main + gh-pages（tg_push_fast 走这个）
python3 -c 'from publish_pages_file import publish_radar_data; raise SystemExit(publish_radar_data())'

# ca_finds
python3 /workspace/project-monitor/publish_ca_finds_pages.py
# 或守护：bash publish_ca_finds_daemon.sh ensure
```

鉴权顺序（`publish_pages_file.py`）：`GITHUB_TOKEN` / `GH_TOKEN` → 文件 `/workspace/project-monitor/.secrets/github_token` → `gh auth token`。  
**软失败**：无 auth 时打印一行并非零退出，不抛崩守护。  
**永不发布**：token 文件名与内嵌密钥值会被拦截（含 `workbench_api_token.txt` 等）。

### 7.2 前端代码部署

- 改 UI / hooks：在 `dushuo1234/pad-hunter` 开 PR → CI/Pages 构建。  
- 已知前端跟进（见 `notes/workbench-auto-prune-frontend.md`）：本地 `localStorage` 工作台 pins 须在 `launchedHandles` / `dropped_launched` 时自动移出，否则会把已开盘项目又 sync 回去。  
- 提醒 UI 规格：`docs/workbench_soon_frontend_spec.md`（只展示 pins 内项目；`confirmed && alert_ok` 才显示「已确认CA」；忽略 `dry_run`）。  
- **不要**在前端发明 `listing_at`；手动已开盘后端 `listing_at=null`。  
- **不要**改 CA 门槛逻辑（`ca_gate` / `ca_confidence.is_ca_fixed`）除非 Ori 明确授权。

### 7.3 CDN / 实时

- 仅靠 Pages 时 CDN 可能滞后数分钟；雷达优先 WS / `/v1/radar/recent`，candidates 前端软轮询 + `?t=` bust。  
- tg_push_fast 有新卡才 publish；30m 例行仍作全量安全网。

---

## 8. 运维检查清单（health、pid、常见故障）

### 8.1 每日 / 接手时

1. `curl -fsS https://api.adualpha.win/health`  
2. `curl -fsS http://127.0.0.1:8780/health`  
3. 各 `*_daemon.sh status`（§3）  
4. `test ! -f .site_scan_paused`  
5. 看日志尾部：  
   - `workbench_api.log` / `workbench_watchdog.log`  
   - `fast_site_poll.log`  
   - `tg_push_fast.log`  
   - `alerts/workbench_soon_watch.log`  
   - `onchain_lock.log` / `tapeout_watch.log`  
   - `sync_manual_launched.log`  
6. Pages 数据是否新鲜：对比本地 `/workspace/push-radar/data/candidates.json` mtime 与站点拉取  
7. WS：浏览器工作台是否连上 `api.adualpha.win`（4401 → token 不一致）

### 8.2 常见故障

| 现象 | 排查 |
|---|---|
| 站点 pins 不同步 | CF health；token 是否与 `workbench_api_token.txt` / Worker secret 一致；DO room 是否旧实例（需升 ROOM_NAME / BUILD_ID） |
| 1033 / 隧道 | 生产应走 **Worker route**，不要依赖已清的 tunnel ingress；`cloudflared` 7844 在本 box 常被拦 |
| ngrok 带宽耗尽 | 已禁用自动 ngrok；`TUNNEL_PROVIDER` 默认 `none` |
| candidates 很旧 | `tg_push_fast` 是否在跑；GH token 是否有效；`publish_radar_data` 返回码；gh-pages 双写是否失败 |
| 已开盘又出现在工作台 | 前端未丢 localStorage；跑/等 `sync_manual_launched`；查 blocklist |
| 官网不扫 | `fast_site_poll` 挂了或 `WORKBENCH_ONLY` 且工作台为空（空 = idle）；watchlist 被 prune |
| 429/backoff | 正常：`fast_site_state.json` 里 host backoff；等恢复 |
| 手动 mark 未进 Pages | `sync_manual_launched_daemon` ensure；看其 log |
| wrangler 未登录 | `npx wrangler login` 后 `bash cf-workbench/deploy.sh` |

### 8.3 Pid / 状态文件速查

| 守护 | pidfile（均在 project-monitor 下） | 主要 log |
|---|---|---|
| workbench API | `workbench_api.pid` (+ tunnel/watchdog) | `workbench_api.log` |
| soon watch | `workbench_soon_watch.pid` | `alerts/workbench_soon_watch.log` |
| fast site | `fast_site_poll.pid` | `fast_site_poll.log` |
| tg push | `tg_push_fast.pid` | `tg_push_fast.log` |
| listing scan | `listing_scan.pid` | `listing_scan_daemon.log` |
| publish ca | `publish_ca_finds_watch.pid` | `publish_ca_finds_watch.log` |
| onchain lock | `onchain_lock.pid` | `onchain_lock.log` |
| tapeout | `tapeout_watch.pid` | `tapeout_watch.log` |
| t20 | `today_t20_watch.pid` | `alerts/today_t20_watch.log` |
| deployer hunt | `today_deployer_hunt.pid` | `alerts/today_deployer_hunt.log` |
| manual launched | `sync_manual_launched.pid` | `sync_manual_launched.log` |

---

## 9. 明确边界与硬规则

1. **Muse 负责**：网站/工作台运行、守护、发布、Worker 健康、前端部署协作、暂停恢复。  
2. **勿越权**：监控策略大改、固定 CA 闸门改写、实盘买卖、项目钱包登录/签名 → 归 Ori 等；本机保持 **server-only、不签钱包**。  
3. **Token**：只引用路径 `workbench_api_token.txt` 与头名 `X-Pad-Hunter-Token`；**永不**粘贴到 GitHub issue/PR/聊天。  
4. **固定 CA 闸**（电报/今日清单出口，Muse 不要绕过）：  
   - 须在今日清单内 + 确认为代币（`is_token`）  
   - 且（① 部署者/关联钱包部署 **或** ② 官推正文发出）  
   - 站点刮取 / 纯高置信 / 仅 quote·转推 → **待确认**，不要当固定 CA 推  
   - 非项目号（个人/KOL bio）、denylist、NFT 等按 `TODAY_T20_README` / `TODAY_TG_DEEPSEEK`  
5. **不编造** `listing_at` / CA。  
6. **Sniper**：`dry_run=true`；本交接不授权改 live。  
7. **Ballast/Baola** 等第三方 feed：confidence low，不当成该项目自身 CA。

---

## 10. 文档索引（本机，继续深挖时读）

| 文件 | 内容 |
|---|---|
| `cf-workbench/README.md` | Worker 端点、部署、room、radar/launched 版本史 |
| `docs/launched_mark_api.md` | 手动已开盘 API |
| `docs/workbench_soon_frontend_spec.md` | 提醒前端规格 |
| `LISTING_CA_README.md` | 扫描流水线、fast_site、workbench 本地 API、prune、tapeout |
| `TODAY_CA_API.md` | `/v1/today/cas` |
| `TODAY_T20_README.md` | T-20 守护与官方号闸 |
| `TODAY_DEPLOYER_HUNT.md` | 部署者猎取 |
| `TODAY_TG_DEEPSEEK.md` | 今日清单电报固定 CA 规则 |
| `notes/tg-push-fast-2026-10-22.md` | TG 近实时路径 |
| `notes/workbench-auto-prune-frontend.md` | 前端自动移出已开盘 |
| `notes/routine_工作台官推高频刷新_prompt_x6551.md` | 官推例行 X/6551 切换 |

---

## 11. 接手后建议第一小时

1. 读本文件 + `cf-workbench/README.md`  
2. 跑 §8.1 检查清单；若用户要跑扫描且无 pause 文件 → 对各守护 `ensure`  
3. 确认 `https://api.adualpha.win/health` 与 Pages `candidates` 时间戳  
4. 不要旋转 token / 不要改 ROOM_NAME，除非同步所有客户端与 `workbench_api_token.txt`  
5. 有前端 bug 开 PR 到 `dushuo1234/pad-hunter`；有 API 行为疑问先查 DO 版本与本 README，再问 Ori

— 完。交接目标：Muse 不询问 Ori 基础运维即可维持站点与工作台运转。
