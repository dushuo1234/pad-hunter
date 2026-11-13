# 青年大学习 → Pad Hunter 项目池

**Asia/Shanghai 2026-10-29**

## Resolved
- Title: `青年大学习` (forum), username `mobai19999`
- peer_id: `-1003870895697` (entity 3870895697)
- Topics: `1=项目推送` (ingest), `5133=聊天`, `5171=hook`, `5136=禁言`
- Config: `/home/box/.tg-monitor/target_qingnian.json`

## Card format
Not 🆕 cards. Freeform:
```
监控到新项目 NAME
推特🔗：https://x.com/handle
粉丝数量：N
…
```
Parser: `parse_qingnian_card` in `fetch_and_classify.py` (`parser=qingnian`).

## Pipeline (same path as 项目推送)
1. `fetch_and_classify.py` now loads `target.json` + `target_fomo.json` + `target_qingnian.json`
2. `sync_site.py` → `push-radar/data/projects.json`
3. `merge_projects_into_candidates.py` → `source=telegram:青年大学习`
4. `publish_pages_file.publish_radar_data`

## Storage
Composite jsonl key `peer:message_id` for non-legacy peers (avoids mid collisions across groups).

## How Fomo was already in projects.json
`source_channel` rows for 币安ai钱包 / gamefi existed, but pre-change `fetch_and_classify` only read `target.json`. Fomo was a prior one-off import + `target_fomo.json` note. Fetch now includes Fomo topics in the same multi-source loop (no second pipeline).

## Smoke (2026-10-29 ~12:52 Asia/Shanghai)
- Fetched 青年 topic1: 80 cards → ~70 unique handles in snapshot
- candidates: 56 with `telegram:青年大学习` (others already present under other TG sources)
- publish_rc=0 (candidates + projects)


## Enrich (2026-10-29 ~14:05 Asia/Shanghai)
- Problem: 青年 freeform cards only had name+handle → site showed 未知/其他/不明/未开盘.
- Module: `/workspace/project-monitor/enrich_qingnian.py` (heuristic from name/bio/posts; optional jina X profile; optional `ds` CN summary). Never invents `listing_at`.
- Wired:
  1. `fetch_and_classify.parse_qingnian` → immediate heuristic enrich; re-fetch preserves filled fields.
  2. `tg_push_fast` after sync → `enrich_qingnian --limit 12` (+ `--jina` when new msgs).
  3. `merge_projects_into_candidates` fills blank fields on **existing** candidates (not only adds).
- One-shot: enriched the 7 digest handles (UBI.fun / Four.meme-華語 / bb / Ryan / ink.fun / Eason / OSBook) via X profile cache + `ds`.
