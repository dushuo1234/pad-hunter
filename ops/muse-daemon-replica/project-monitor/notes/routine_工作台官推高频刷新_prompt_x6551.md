# Routine update draft — 工作台官推高频刷新 (automation-1792771375222)

Parent: UpdateRoutine get → update with this prompt intent (do not bake MCP schemas).
Schedule: keep existing `@every 5m` (or whatever is currently saved).

## Prompt (intent)

工作台官推高频刷新。每轮按下面顺序做，完成后默认对用户保持安静（除非有额度以外的可行动异常）。

1. 先读磁盘状态与计划：
   - 跑 `python3 /workspace/project-monitor/workbench_soon_x_fetch.py maybe-restore`（UTC 日切过后会自动翻回内置 X）。
   - 再跑 `python3 /workspace/project-monitor/workbench_soon_x_fetch.py run`，看返回的 `action`。

2. 若 `action=USE_X`（或 status.mode=x）：
   - 读 `alerts/workbench_soon_x_plan.json` 的 `search_queries`。
   - 用内置 X 的帖子搜索（search_posts_all 一类）按每条 query 拉最近约 2 小时、按时间新到旧、最多约 50 条，带作者与正文时间字段。
   - 把每条 query 的原始 JSON（去掉工具包装）写入 `alerts/x_inbox/<unix_ts>_<i>.json`，形状与平时一致。
   - 若任一搜索报日额度用尽 / usage capped / 1000 limit / daily read limit：不要只记日志；立刻跑  
     `python3 /workspace/project-monitor/workbench_soon_x_fetch.py on-quota --reason '<简短错误>'`  
     它会写入 `alerts/x_quota_fallback.json`（mode=6551）并用 6551 拉今日优先 handles，写入同目录 x_inbox（source=6551）。然后本轮结束。
   - 额度类错误可追加一行到 `alerts/workbench_soon_x_fetch_errors.log`，但**不要因此打扰用户**。

3. 若 `action=USE_6551`（或 status.mode=6551）：
   - **不要**再调内置 X 搜索（避免空烧额度探测以外的调用）。
   - `run` 已触发 6551 拉取则无需再拉；若 `fetch.skipped` 仅因间隔，可接受。
   - 若想在新 UTC 日探测额度是否恢复：最多做一次极轻量的内置 X 搜索；成功则  
     `python3 .../workbench_soon_x_fetch.py mark-x-ok --reason 'probe ok'`；  
     仍额度满则保持 6551，不要刷屏。

4. 不要动 T-20 / today_t20_watch / sniper_6551 WSS。不要宣称或执行固定 CA 买入。不要把 6551 token 写进日志或回复。

5. 交付：本轮结果只留在磁盘（x_inbox + x_quota_fallback.json）。对用户保持安静；只有非额度类、需要人工处理的故障才在本聊天简短说一句。

Who receives the result: no one (quiet). When nothing new / only quota fallback: stay silent to the user in this chat.
