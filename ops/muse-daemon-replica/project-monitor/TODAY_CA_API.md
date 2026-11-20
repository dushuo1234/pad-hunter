# 今日项目清单 · 实时 CA API

给本地机器人最快拉 CA。公网：`https://api.adualpha.win`

鉴权：请求头 `X-Pad-Hunter-Token`（与工作台同 token，在 box `workbench_api_token.txt`，勿贴聊天）。

## 拉取（推荐轮询 1–2s，或挂 WS）

```bash
curl -sS -H "X-Pad-Hunter-Token: $TOKEN" \
  "https://api.adualpha.win/v1/today/cas"
```

增量：

```bash
curl -sS -H "X-Pad-Hunter-Token: $TOKEN" \
  "https://api.adualpha.win/v1/today/cas?since=2026-10-28T16:00:00+08:00"
```

返回要点：
- `projects[]`：今日清单；每项有 `chain` / `chain_note`（如 `链:BSC`）
- `projects[].best_ca`：该项目当前最优 CA；含 `ca`、`chain`、`chain_note` / `wallet_note`（格式 `[robinhood] 0x…`）
- `events[]`：CA 事件流（新发现追加）；同样带 `chain` + `wallet_note`

## WebSocket（最快）

连 `wss://api.adualpha.win/v1/workbench/ws?token=$TOKEN`  
握手后有 `type: today_cas`；扫到新 CA 会推 `type: today_ca`（带 `events` + 完整 `state`）。

## 推送源（box 自动）

- `today_ca_push.py sync`：清单 tick 每 15 分钟全量同步
- T-20 / 部署者猎取：扫到 CA 立刻 `POST /v1/today/cas/push`（单事件）
