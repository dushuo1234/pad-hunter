# 台子雷达 / Pad Hunter

中文优先的项目雷达。页面读取 Telegram「项目推送」和「项目推送监控」整理出的 JSON，按 **链** 和 **类型 / 发射台** 筛选，不用登录。每条项目可以打开 **监控详情**，导航里另有 **今日开盘**。

技术栈：Vite + React + TypeScript + Tailwind CSS。

## 本地运行

```bash
npm install
npm run dev
```

浏览器打开终端提示的本地地址（默认 `http://localhost:5173/pad-hunter/`）。

生产构建：

```bash
npm run build
npm run preview
```

## 线上地址

GitHub Pages 已指向 `gh-pages` 分支：<https://dushuo1234.github.io/pad-hunter/>

合并到 `main` 后，`.github/workflows/pages.yml` 会执行 `npm run build`，并把 `dist` 推到 `gh-pages`。不需要再改 Pages 设置。Pull request 上同一工作流只构建、不发布。

## 数据文件

默认从 `public/data/candidates.json` 加载。文件可以同时包含两个频道。顶层 `sources` 列出频道，每条 candidate 用自己的 `source`（`telegram:项目推送` 或 `telegram:项目推送监控`）。缺省时界面回退到顶层 `source`。卡片上的来源徽章显示频道名。

| 字段 | 含义 |
| --- | --- |
| `name` / `handle` | 项目名、X 账号 |
| `chain` | 链 |
| `category` | 类型 / 发射台（发射台、Meme币、GameFi、NFT铸造、DeFi协议、AI代理、基础设施、其他…） |
| `status` | 状态 |
| `listing` | 开盘 |
| `risk` | 风险 |
| `why` / `bio` | 中文摘要 / 英文简介 |
| `tweet_url` | X 链接 |
| `date_iso` / `message_id` | 推送时间、Telegram 消息 id |
| `source` | 频道，`telegram:项目推送` 或 `telegram:项目推送监控` |
| `ca` / `ca_chain` / `ca_source` | 已发现的合约，可空 |
| `listing_signal` / `sites` / `last_checked` | 最近开盘信号、站点、检查时间，可空 |
| `rank` / `score` / `followers` / `kol_followers` | 兼容旧版卡片的排序字段。`followers` 可以是数字，或 `粉丝 188 · 你圈子 1 人` 这种原文 |

顶层还有 `generated_at_utc`、`goal`、`source`、`sources`。

页面右上角 **刷新** 会重新请求这份 JSON（适合按日替换文件后看新数据）。**上传 JSON** 只替换当前会话，刷新页面后恢复仓库里的文件。

## 从 Telegram 重新生成

监控脚本在 `scripts/telegram/`。它们读取环境变量或未跟踪的 `scripts/telegram/.env`，把卡片写成上面的 JSON。**不要提交 `.env`、Telethon `*.session` 或 `scripts/telegram/.data/`。**

```bash
cp scripts/telegram/env.example scripts/telegram/.env
# 在 .env 里填写 TG_API_ID、TG_API_HASH、TG_PEER（不要把填好的文件提交）

python3 -m venv scripts/telegram/.venv
scripts/telegram/.venv/bin/pip install -r scripts/telegram/requirements.txt
# 首次在本机交互登录，生成 session。步骤见 scripts/telegram/README.md

python3 scripts/telegram/sync_site.py --limit 200
```

`sync_site.py` 会更新 `public/data/candidates.json`。之后重新 `npm run build`。每天跑一次即可，例如：

```cron
0 8 * * * cd /path/to/pad-hunter && python3 scripts/telegram/sync_site.py --limit 200
```

环境变量说明、代理和离线自测：见 [scripts/telegram/README.md](scripts/telegram/README.md)。

离线检查解析（不覆盖正式数据）：

```bash
python3 scripts/telegram/sync_site.py --offline --out /tmp/pad-hunter-sample.json
```

## 功能一览

- Hero：项目数、类型数、覆盖链、北京时间更新时间
- **类型 / 发射台** 筛选芯片。点一个类型，下面只显示该类型的项目；「全部」是一条总列表
- 链、搜索、粉丝、KOL 筛选，以及最新 / 评分 / 粉丝 / KOL 排序，都作用在当前列表上
- 卡片带类型、状态、开盘徽章，以及来源（项目推送 / 项目推送监控）
- 卡片上的 **监控详情** 进入该项目的时间线
- 导航 **今日开盘**：mint进行中、即将启动、开盘信号，或文案里写了今天日期的项目
- 导航 **发现CA**：按项目列出扫到的合约地址，每秒重读 `ca_finds.json`
- 导航 **工作台**：钉住关心的项目，写个人备注，并对照监控进度
- 卡片和监控详情上的 **加入工作台** 把项目钉到本机工作台
- 详情侧栏：摘要、风险、开盘、X 链接，可再进监控详情
- 浅色 / 深色主题

## 监控详情与今日开盘

- 项目列表：`/pad-hunter/`
- 今日开盘：`/pad-hunter/today`
- 发现CA：`/pad-hunter/ca`
- 工作台：`/pad-hunter/workbench`
- 某个项目：`/pad-hunter/monitor/<handle>`，例如 `/pad-hunter/monitor/SpareFluxAi`

GitHub Pages 会把 `dist/index.html` 复制成 `404.html`，所以这些路径刷新后仍能打开。

工作台的钉选和备注只写在浏览器 localStorage（键名 `pad-hunter.workbench.v1`），不经过服务器。页面可以导出 JSON 备份，导入 JSON 会替换当前工作台。刷新页面后还在；清除站点数据会丢掉，所以换浏览器前先导出。

监控时间线读 `public/data/monitor_events.json`。没有事件时详情页是空时间线，项目列表不受影响。`sample: true` 的事件只出现在时间线上，并标成「示例」，不会当成当前合约。

### 以后怎么写入真实事件

保持 `handle` 和 `candidates.json` 里的 handle 一致（大小写不敏感）。追加到 `events`，或把扫描器原文嵌进同一个文件。页面会合并这些形状：

| 位置 | 来源形状 | 变成 |
| --- | --- | --- |
| `events[]` 且 `kind: "site"` | `site` 同 `latest.json` 的 `results[]`（`url`、`status`、`http_code`、`time_s`、`error`） | 站点可用 / 不可用 |
| `events[]` 且 `kind: "listing_signal"` | `listing_signal` 同 `new_listing_signals[]`（`signal`、`prev`） | 开盘信号 |
| `events[]` 且 `kind: "ca"` | 同 watchlist 的 `ca`、`ca_chain`、`ca_source` | 发现合约 |
| `events[]` 且 `kind: "factory"` | `factory_deploy`：`chain`、`tx`、`factory`、`token`、`block`、`notes` | 工厂部署 |
| `latest` | 整份 `latest.json` | 站点事件 |
| `listing_scan` | 整份 `listing_scan_latest.json`（`new_listing_signals`、`results[].sites`、`cas`、`signals`、`new_cas`） | 站点、信号、合约 |
| `watchlist` | 整份 watchlist（`projects[].ca`、`listing_signal`） | 合约、信号 |
| `factory_deploys[]` | 同上工厂字段，另加 `handle`、`name`、`at` | 工厂部署 |
| `files` | 相对 `public/data/` 的路径，例如 `monitor/thetimecard.json`，文件内容同样是上述任一形状 | 合并进时间线 |

示例：

```json
{
  "generated_at": "2026-10-20T03:14:08Z",
  "events": [
    {
      "id": "site|sparefluxai|2026-10-20T11:06:40+08:00|https://spareflux.netlify.app/",
      "kind": "site",
      "at": "2026-10-20T11:06:40+08:00",
      "handle": "SpareFluxAi",
      "name": "SpareFlux",
      "site": {
        "url": "https://spareflux.netlify.app/",
        "status": "up",
        "http_code": "200",
        "time_s": 0.222,
        "final_url": "https://spareflux.netlify.app/",
        "error": ""
      }
    }
  ]
}
```

已有扫描文件时可以直接转成这份 JSON：

```bash
python3 scripts/monitor/build_monitor_events.py \
  --latest latest.json \
  --listing-scan listing_scan_latest.json \
  --watchlist watchlist.json \
  --out public/data/monitor_events.json
```

`--samples` 会额外写入两条标成示例的合约和工厂事件，只用于看时间线样式。正式数据不要加这个参数。

两个频道一起留在站点文件里时，同步其中一个频道加上 `--merge`，并指定来源：

```bash
TG_SOURCE='telegram:项目推送监控' python3 scripts/telegram/sync_site.py --limit 200 --merge
```

不加 `--merge` 时，脚本仍会整份覆盖 `candidates.json`（每条会带上 `source`）。

## 发现CA

`/pad-hunter/ca` 读取 `public/data/ca_finds.json`，每秒带 `?t=` 重新请求。打开页面之后新写入的行会高亮。可以按链、置信度筛选，并用项目名或地址搜索。每条地址可以复制、打开对应浏览器（Etherscan、Solscan、Basescan 等），并进入该项目的监控详情或加入工作台。

`confidence` 为 `low` 时页面会标成低置信。这用来放第三方弱信号，例如 Baola、Ballast 等信息流站点上的代币图标，不一定是项目自己公布的合约。

```json
{
  "generated_at": "2026-10-20T00:00:00.000Z",
  "finds": [
    {
      "project": "项目名",
      "handle": "X账号",
      "chain": "Base",
      "address": "0x…",
      "source": "site",
      "evidence_url": "https://example.com/evidence",
      "detected_at": "2026-10-20T08:00:00.000Z",
      "confidence": "high",
      "note": ""
    }
  ]
}
```

`source` 取 `site`、`js`、`x`、`tg`、`on-chain`。`confidence` 取 `high` 或 `low`。发现时间按北京时间（Asia/Shanghai）显示。没有发现时 `finds` 为空数组。

## 设计说明

视觉沿用奶油底、橙色强调、等宽标签和雷达动效，信息按链和类型排开，方便扫读。
