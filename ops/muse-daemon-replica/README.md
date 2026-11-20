# Muse 守护复刻源码（不含密钥）

本目录是 Pad Hunter box 守护的**无密钥**代码与状态树，供 Muse 虚拟机从 GitHub 拉取后复刻。对应 2026-11-04 的消毒包 `pad-hunter-daemons-src-20261104.tar.gz`（不是含活密钥的 FULL 包）。

顶层目录：

- `project-monitor/` — 守护脚本、`cf-workbench/`、文档与非密钥状态 JSON
- `push-radar/` — 静态站点片段与当前 `data/*.json`
- `tg-monitor-code/` — Telethon / 分类脚本（无 session、无 `.env`）

## 密钥不在 git

**token、Telegram session、`.env` 都不在本仓库。** adu 另行把密钥交给 Muse。键名与相对路径见 `SECRET_KEYS.md`（只有名称，没有值）。录入 Muse 保险库后，按该文件的路径放回工作目录，并对 token / session 文件执行 `chmod 600`。不要把值写入 git、Issue 或聊天。

入库前从包内删掉的误带文件：

- `project-monitor/cf-workbench/.dev.vars`（含 `WORKBENCH_TOKEN`）
- `project-monitor/ngrok.yml`（含 ngrok `authtoken`）
- `project-monitor/cf-workbench/.wrangler/`（本机 wrangler / miniflare 缓存，不是源码）

`sniper_config` 只保留 `project-monitor/sniper_config.redacted.json`（`token_6551` 已抹成 `REDACTED`，`dry_run` 仍为 true）。

## 影子期，禁止双发

Muse 侧先进入影子期：不向 GitHub Pages 发布、不向 Worker 推雷达、不发 alerts，只和 box 侧对账。对账连续一致后再约切换。切换时 box 先停发布类守护，确认停稳后 Muse 再开。**两边不得同时发布**（Contents API 会互相覆盖，雷达会重复推送）。回滚时先停 Muse 侧发布，再恢复 box。

细则：`project-monitor/notes/muse-daemon-replica-checklist-2026-11-04.md`。

## 网站运行交接

仓库根的 `docs/muse-website-runtime-handoff.md` 尚未进入 `main`，见 [PR #52](https://github.com/dushuo1234/pad-hunter/pull/52)。合并后以该路径为准。本树里有一份副本：`project-monitor/docs/muse-website-runtime-handoff.md`。

## 本目录清单

- `PACK_MANIFEST.md` — 打包范围、SRC / FULL 差异、排除项
- `SECRET_KEYS.md` — 密钥路径与用途（仅名称）
