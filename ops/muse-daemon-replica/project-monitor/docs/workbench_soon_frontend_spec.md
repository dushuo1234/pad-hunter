# 前端规格：工作台每个项目的实时提醒（即将开始 / CA / 官网·JS 变动）

所有展示给用户的文字都用中文。**不要**改 CA 门槛逻辑，**不要**写 `listing_at`。

## 后端（已上线，不需要改）
Worker `https://api.adualpha.win`（1.7.2-cf，room `pad-hunter-v6`）新增：

| 方向 | 内容 |
|---|---|
| WS hello（连接/重连后） | `{"type":"workbench_alerts","state":{"updated_at","count","items":[Alert…]},"event":"hello"}`：最近 200 条，按 `ts` 倒序 |
| WS 实时 | `{"type":"workbench_alert","alerts":[Alert…],"origin_client_id":"box-workbench-soon"}`，只发新增的 |
| WS 联调 | 同上但带 `"dry_run": true`。**前端必须忽略 dry_run 消息**（不显示、不存） |
| GET `/v1/workbench/alerts` | 需要 token，返回同 `state`（WS 不通时轮询兜底，60s 一次） |

### Alert 结构（字段都可能为 null）
```jsonc
{
  "id": "16位hex",            // 唯一去重键
  "ts": "2026-10-24T00:01:00+08:00",   // 发现时间（北京时间）
  "handle": "CaravanRH",       // 和工作台 pin 的 handle 对应（不区分大小写，去掉 @）
  "name": "CaravanRH",
  "kind": "x_post" | "site_time" | "ca" | "ca_signal" | "js_address" | "site_change" | "js_change",
  "summary": "【CaravanRH】官推说即将开始：11/01 20:00（北京时间）",   // 直接显示的中文一句话
  "start_at": "2026-11-01T20:00:00+08:00", "start_at_display": "11/01 20:00（北京时间）",
  "has_clock": true, "tz_note": "UTC", "is_delay": false, "prev_start_at": null,
  "address": "0x…", "chain": "robinhood",
  "ca_status": "confirmed" | "candidate" | "suspected_copycat" | "nft" | "superseded" | "unconfirmed",
  "ca_status_zh": "已确认CA（官推确认）", "alert_ok": false,
  "evidence_url": "https://…", "quote": "原文片段",
  "baseline": true,            // 守护进程首次启动时的存量，不是刚发生的
  "source": "x" | "site_html" | "site_js" | "ca_finds" | "fast_site:SITE_CHANGE" | …
}
```

## 前端改动
1. **WS 处理**（现有 `workbench` WS 客户端，已处理 pins/radar/launched 的那个文件）：
   - `workbench_alerts`（hello）：整体替换本地 `wbAlerts`；`workbench_alert`：按 `id` 去重插入到最前；`dry_run===true` 直接丢弃。
   - 保存到 `localStorage`（key 如 `ph.wbAlerts.v1`，最多 200 条）以便刷新后先显示。
   - WS 断开时用 GET `/v1/workbench/alerts` 60s 轮询兜底（沿用现有 token 头 `X-Pad-Hunter-Token`）。
2. **按项目归并**：`alertsByHandle = groupBy(norm(handle))`，每个项目算出：
   - `soon`：最新一条 kind ∈ {x_post, site_time}
   - `ca`：最新一条 kind=ca（同一地址以最新状态为准）；没有时取最新 ca_signal / js_address
   - `change`：最新一条 kind ∈ {site_change, js_change}
3. **工作台每行（和详情面板）显示**，在项目名下方加一个提醒区，最多 3 行：
   - ⏰ 即将开始：`summary`（去掉开头【名称】）+ `start_at_display`；`is_delay` 时加红色「延期」徽章；hover/点开显示 `quote` + 链接 `evidence_url`（文字「来源」）。
   - 🪙 CA：
     - `ca_status=confirmed && alert_ok===true` → 绿色徽章「已确认CA」+ 短地址 + 复制按钮 + 链名。
     - `candidate` / `unconfirmed` → 黄色「待核验」；`nft` → 灰色「NFT 合约·不算CA」；`suspected_copycat` → 灰色「疑似山寨·不算CA」；`superseded` → 灰色「旧CA」。
     - 只有 confirmed+alert_ok 才能用绿色/「已确认CA」字样；其他状态绝不能显示成已确认。
   - 🔧 官网/JS：`summary` + 相对时间（如「3 分钟前」）。
   - 每行右侧显示相对时间（用 `ts`）。
4. **高亮**：收到非 baseline 的新提醒时，该项目行高亮 30 秒（黄色背景渐隐）并在行上显示「新」小红点，直到用户点开该项目或点「已读」。`baseline:true` 的不高亮、不弹提示，只静默显示。
   - kind ∈ {x_post, site_time} 且 `start_at` 在 24 小时内，或 `kind=ca && ca_status=confirmed`：额外弹一次页面右上角 toast（中文 summary），可点击跳到该项目行。
5. **排序**：不改现有排序规则（推送日期最新优先）。提醒只是行内信息。
6. **已开盘**：项目被「确认已开盘」或进入 blocklist 后，不再显示它的提醒（后端也会停止推送）。
7. **只展示工作台里的项目**：handle 不在当前 pins 里的提醒忽略（保留在内存里即可，用户重新加入工作台后会显示）。

## 测试
- 加一个 fixture（例如 `scripts/fixtures/workbench_alerts.json`）覆盖每个 kind 和每个 ca_status，并在现有 `npm test` 的 check 脚本里断言：
  - 只有 `confirmed && alert_ok` 渲染「已确认CA」；`nft` / `suspected_copycat` 渲染「不算CA」。
  - `dry_run` 消息被忽略；同 `id` 只出现一次。
  - 所有提醒文案里没有英文句子（复用 check-upcoming-and-notes 的英文检查思路，地址/链接/`quote` 原文除外）。
