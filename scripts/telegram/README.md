# Telegram 「项目推送」数据管道

把 Telegram 群「项目推送」里的项目卡片解析成台子雷达使用的 `public/data/candidates.json`。前端仍是 Vite + React，只读这份 JSON。

脚本不会打印 API hash、代理密码或 session 内容。本地快照、jsonl 和 Telethon session 默认写到 `scripts/telegram/.data/`，该目录已在 `.gitignore` 里。

## 环境变量

复制 `env.example` 为 **未跟踪** 的 `scripts/telegram/.env`（或导出同名变量）。进程环境覆盖文件。

| 变量 | 必填 | 说明 |
| --- | --- | --- |
| `TG_API_ID` | 是 | [my.telegram.org](https://my.telegram.org) 的数字 app id |
| `TG_API_HASH` | 是 | 对应的 app hash |
| `TG_PEER` | 是 | 「项目推送」的 peer：数字 id（如 `-100…`）或 `@username` |
| `TG_SESSION` | 否 | Telethon session 路径，默认 `scripts/telegram/.data/tg.session` |
| `TG_DATA_DIR` | 否 | 快照 / jsonl / 看板输出目录，默认 `scripts/telegram/.data` |
| `TG_ENV_FILE` | 否 | env 文件路径，默认 `scripts/telegram/.env` |
| `TG_TARGET_FILE` | 否 | 若不设 `TG_PEER`，从此 JSON 读取 `peer_id` / `id` / `username` |
| `TG_PROXY_TYPE` | 否 | `http` 或 `socks5`，默认 `http` |
| `TG_PROXY_HOST` | 否 | 代理主机 |
| `TG_PROXY_PORT` | 否 | 代理端口 |
| `TG_PROXY_USER` | 否 | 代理用户名 |
| `TG_PROXY_PASS` | 否 | 代理密码 |

不要把填好的 `.env`、`*.session`、`*.session-journal` 或 `.data/` 提交到 git。

## 一次性登录

在你自己的机器上创建 session（交互式，会要求手机号与验证码）。session 文件留在本机：

```bash
python3 -m venv scripts/telegram/.venv
scripts/telegram/.venv/bin/pip install -r scripts/telegram/requirements.txt
scripts/telegram/.venv/bin/python - << 'PY'
import os
from pathlib import Path
from telethon.sync import TelegramClient

root = Path("scripts/telegram/.data")
root.mkdir(parents=True, exist_ok=True)
# export TG_API_ID / TG_API_HASH first, or load them from scripts/telegram/.env yourself
client = TelegramClient(str(root / "tg.session"), int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"])
client.start()
print("session authorized")
client.disconnect()
PY
```

## 刷新站点数据

```bash
python3 scripts/telegram/sync_site.py --limit 200
```

这会：

1. 拉取最近 200 条消息并解析以 `🆕` 开头、带 `⛓ 链 · 类型` 的卡片
2. 按 handle 去重，写入 `scripts/telegram/.data/projects.json`
3. 转成台子雷达 schema，覆盖 `public/data/candidates.json`。每条带 `source`（默认 `telegram:项目推送`，也可用 `TG_SOURCE` 或 `--source`）。要保留文件里另一个频道的项目，加上 `--merge`。

字段对应：`name`、`handle`、`chain`、`category`（发射台 / Meme币 / GameFi / NFT铸造 / DeFi协议 / AI代理 / 基础设施 / 其他）、`status`、`listing`（开盘）、`risk`、`why`（中文摘要）、`bio`、`tweet_url`、`date_iso`、`message_id`。

只转换已有快照、不再请求 Telegram：

```bash
python3 scripts/telegram/sync_site.py --no-fetch
```

不连 Telegram、用仓库里的样例卡片自测解析（输出到临时文件，避免覆盖正式数据）：

```bash
python3 scripts/telegram/sync_site.py --offline --out /tmp/pad-hunter-sample.json
```

## 定时

每天早上刷新一次即可。cron 示例（路径按部署机器修改）：

```cron
0 8 * * * cd /path/to/pad-hunter && python3 scripts/telegram/sync_site.py --limit 200
```

刷新后的 `public/data/candidates.json` 可以提交并重新 `npm run build`。session 与 `.env` 不要一起提交。
