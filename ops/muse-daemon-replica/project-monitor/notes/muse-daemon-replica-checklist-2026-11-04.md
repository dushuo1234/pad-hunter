# Pad Hunter 守护复刻到 Muse 环境：交接清单

> 2026-11-04 adu 拍板第 2 种：在 Muse 的环境里复刻整套 box 守护。
> Muse 侧环境已实测：Linux x86_64、4 核、磁盘可用 147G、Python 3.12.3、Node 24、systemd 可用（守护可用 systemd 托管，VM 换代可自恢复）；内存余量偏紧，部署后要盯。
> **铁律：任何 token、TG session、.env 内容不要粘贴到聊天或提交进 git；密钥一律走 Muse 安全保管。**

## 一、需要从 box 打包给 Muse 的源码（不含密钥）

在 box 上打包 `/workspace/project-monitor` 与相关目录，**排除**下列项后，把压缩包给 Muse（在本对话上传，或放进一个私有仓库/分支）：

打包范围：
- `/workspace/project-monitor/` 全部脚本与源码：各 `*_daemon.sh`、`workbench_api.py`、`cf-workbench/`、扫描与构建脚本（`scan_*`、`build_ca_finds.py`、`publish_pages_file.py`、`publish_ca_finds_pages.py`、`merge_*`、`prune_*`、`run_listing_onchain_js.sh` 等）、各 README 与 docs/、notes/
- `/workspace/push-radar/` 的代码部分（`sync_site.py` 调用方、merge 脚本）
- `/home/box/.tg-monitor/` 里的 `sync_site.py` 等代码文件（**不含** session，见第二节）
- 当前状态快照（非密钥，接续要用）：`watchlist.json`、`ca_finds.json`、`workbench_active.json`、`workbench_reviewed.json`、`fast_site_state.json`、今日清单相关 json

排除（绝不打包）：
- `.secrets/`（含 github_token）
- `workbench_api_token.txt`
- 任何 `*.env`、含真实密钥的 config（如 sniper_config.json 里的密钥字段，结构可给、值抹掉）
- Telegram 的 `*.session` 文件
- `alerts/`、各类 `*.log`、`*.pid`、`__pycache__/`

## 二、密钥清单（只走 Muse 安全保管，逐个给，不要打包）

1. GitHub 发布用 token（对应 box 上 `.secrets/github_token`，用于 Contents API 发布 Pages 数据）
2. 工作台 token（对应 `workbench_api_token.txt`，请求头 `X-Pad-Hunter-Token`；同时是 Worker 的 `WORKBENCH_TOKEN` secret）
3. Telegram：api_id / api_hash 与 Telethon session（tg_push_fast 用；session 等同账号登录态，务必只走保管。若不便给 session，可改走重新授权登录流程，再议）
4. 其他脚本实际用到的键（Helius 等）：Ori 只需列出**键名和用途**，值逐个走保管录入

## 三、复刻与切换协议（防双写）

1. **影子期**：Muse 侧守护先以不发布方式跑：不执行 publish 到 GitHub、不 POST radar 到 Worker、不推 alerts；只比对产出（candidates / ca_finds 与 box 侧是否一致）。
2. **对账**：影子产出与 box 侧连续若干轮一致后，再约切换时间点。
3. **切换**：box 侧先停发布类守护（`publish_ca_finds`、`tg_push_fast`、`onchain_lock`、`sync_manual_launched` 等含发布动作的），确认停稳后 Muse 侧再开启发布。**严禁两边同时发布**（Contents API 双写会互相覆盖、雷达会重复推送）。
4. **回滚**：切换后发现问题，先停 Muse 侧发布，再恢复 box 侧守护。

## 四、不在复刻范围 / 需另行确认

- Cursor 例行（项目推送监控、官网探活、开盘与CA预警、官网秒级CA快报、工作台官推高频刷新、今日项目清单）调度在 Cursor Routines，业务判断归 Ori，不随守护复刻迁移；但例行会触发 box 上的批处理流水线 `run_listing_onchain_js.sh`，复刻后这批脚本在 Muse 侧，触发方式需再定（可由 Muse 侧定时任务替代触发，业务口径仍归 Ori）。
- 监控策略、CA 闸门（`ca_gate`）调参、买卖、钱包签名：不复刻、不迁移，仍归 Ori；sniper 保持 `dry_run=true`。
