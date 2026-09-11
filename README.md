# 台子雷达 / Pad Hunter

中文优先的 Launchpad **产品**猎人前端 —— 发现正在建造「台子」的团队，而不是 pump/pons 上的 meme 代币。

技术栈：Vite + React + TypeScript + Tailwind CSS。无需登录。

## 本地运行

```bash
npm install
npm run dev
```

浏览器打开终端提示的本地地址（默认 `http://localhost:5173`）。

生产构建：

```bash
npm run build
npm run preview
```

## 数据文件

默认从 `public/data/candidates.json` 加载候选项目。

### 替换默认数据

1. 用你的结果覆盖 `public/data/candidates.json`
2. 保持结构大致如下：

```json
{
  "generated_at_utc": "2026-09-11T00:00:00+00:00",
  "goal": "可选说明",
  "candidates": [
    {
      "rank": 1,
      "handle": "example",
      "name": "Example Pad",
      "followers": 1000,
      "kol_followers": 5,
      "bio": "…",
      "why": "为什么值得关注",
      "score": 100,
      "tweet_url": "https://x.com/…",
      "chain": "Solana",
      "notes": "可选"
    }
  ]
}
```

3. 重新 `npm run dev` / `npm run build`

### 会话内临时替换

页面右上角 **上传 JSON** 可在不改仓库文件的情况下，用本地 JSON 替换当前会话数据（刷新后恢复默认）。

## 功能一览

- Hero 统计：追踪项目数、平均评分、覆盖链
- 卡片 Feed：排名、评分、handle、粉丝、KOL、链、why、X 链接
- 筛选：搜索、链、最低粉丝、最低 KOL
- 排序：评分 / 粉丝 / KOL
- 详情侧栏
- 浅色 / 深色主题切换

## 设计说明

视觉参考 AlphaRadar：奶油底、橙色强调、等宽字体标签、雷达动效，追求干净可扫读（scannable）的信息密度。
