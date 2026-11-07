# 项目雷达 · PushRadar

电报「项目推送」群的本地分类看板（独立产品，非 AlphaRadar）。

## 打开方式

**推荐（避免浏览器拦截本地 JSON）：**

```bash
cd /workspace/push-radar
python3 -m http.server 8765
```

然后在浏览器打开：http://127.0.0.1:8765/

也可以直接双击 / 打开 `index.html`（部分浏览器对 `file://` 下的 `fetch` 有限制）。

## 目录

- `index.html` — 单页看板
- `assets/style.css` / `assets/app.js` — 样式与交互
- `data/projects.json` — 最新项目快照

## 同步数据

从电报拉最新消息并刷新站点数据：

```bash
/home/box/.tg-monitor/venv/bin/python /home/box/.tg-monitor/sync_site.py --limit 100
```

仅复制已有快照、不连电报：

```bash
python3 /home/box/.tg-monitor/sync_site.py --offline
```

## 功能

- 深色看板 / 网格双视图
- 按 **链**、**类型**（发射台、Meme币、GameFi、NFT铸造、DeFi协议…）筛选
- 搜索项目名 / @handle / 摘要
- 卡片展示：链徽章、类型、状态、开盘、摘要、X 链接、时间（Asia/Shanghai）
- 顶部统计条：总数与链 / 类型分布

## 注意

同步脚本会使用已有 Telethon 会话与代理配置；请勿把凭证打印到日志或提交到公开仓库。
