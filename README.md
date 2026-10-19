# 台子雷达 / Pad Hunter

中文优先的项目雷达。页面读取 Telegram 群「项目推送」整理出的 JSON，按 **链** 和 **类型 / 发射台** 筛选，不用登录。

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

默认从 `public/data/candidates.json` 加载。当前文件是 Telegram「项目推送」的分类结果（来源字段 `telegram:项目推送`），每条包含：

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
| `rank` / `score` / `followers` / `kol_followers` | 兼容旧版卡片的排序字段 |

顶层还有 `generated_at_utc`、`goal`、`source`。

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
- **类型 / 发射台** 筛选芯片，以及链、搜索、粉丝、KOL 筛选
- 看板：按类型分列；列表：带类型、状态、开盘徽章的卡片
- 排序：最新 / 评分 / 粉丝 / KOL
- 详情侧栏：摘要、风险、开盘、X 链接
- 浅色 / 深色主题

## 设计说明

视觉沿用奶油底、橙色强调、等宽标签和雷达动效，信息按链和类型排开，方便扫读。
