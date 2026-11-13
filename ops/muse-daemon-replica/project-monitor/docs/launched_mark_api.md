# Pad Hunter — 手动确认已开盘 API (Worker 1.7.1-cf)

Base: `https://api.adualpha.win`  
Auth: header `X-Pad-Hunter-Token` (same as workbench). WS: `wss://api.adualpha.win/v1/workbench/ws?token=…`  
Room: `pad-hunter-v5`

## POST `/v1/launched/mark`

Mark a project as 已开盘 from the website.

Request JSON:
```json
{
  "handle": "SomeHandle",
  "name": "可选显示名",
  "reason": "manual",
  "at": "可选 ISO8601；默认服务器 Asia/Shanghai now",
  "client_id": "site-manual",
  "source": "manual"
}
```

Response 200:
```json
{
  "ok": true,
  "mark": {
    "handle": "SomeHandle",
    "name": "可选显示名",
    "reason": "manual",
    "at": "2026-10-23T17:49:50+08:00",
    "client_id": "site-manual",
    "source": "manual"
  },
  "already_blocked": false,
  "blocklist_count": 52,
  "dropped_launched": [{"handle": "…", "name": "…"}],
  "pins": {"synced_at": "…", "items": [], "removed": []},
  "launched": {"updated_at": "…", "count": 1, "items": [], "handles": [], "blocklist_count": 52},
  "radar_removed": false
}
```

Effects (durable DO storage):
- handle → blocklist (rejects future pin re-adds)
- append/upsert `manual_launched` audit (last 500, newest first)
- matching pins tombstoned + WS `pins`
- matching radar cards dropped + WS `radar` / `radar_delta` (`removed_handles`)
- WS also broadcasts `launched_mark` and `blocklist`

Errors: `400` missing handle; `401` bad/missing token.

## GET `/v1/launched/recent`

```json
{
  "updated_at": "…",
  "count": 1,
  "items": [{"handle":"…","name":"…","reason":"manual","at":"…","client_id":"…","source":"manual"}],
  "blocklist_count": 52,
  "blocklist_updated_at": "…",
  "handles": ["…"]
}
```

Use on page load to filter stale static `candidates.json` / cards.

## Related (unchanged / aligned)

- `GET|POST /v1/workbench/blocklist` — prune scripts; GET also returns `manual_count`, `manual_updated_at`
- Blocklist POST `mode:"replace"` **unions** durable manual marks (box prune cannot wipe a fresh site tap)
- Radar: `POST /v1/radar/push`, `GET /v1/radar/recent` still live
- WS hello now also sends `blocklist` + `launched` snapshots

## Frontend notes

1. On button tap → `POST /v1/launched/mark` with `{handle, name?, reason:"manual", client_id}`.
2. Optimistically remove card from all lists; also listen WS `launched_mark` / `blocklist` / `pins` / `radar_delta`.
3. Do not invent `listing_at`; backend leaves it null for manual marks.
4. 401 / close 4401 → token mismatch.

## Box sync

`sync_manual_launched.py` daemon (~45s) pulls `/v1/launched/recent` → `removed_launched.json` (`reason=manual`, `listing_at=null`) → prune watchlist/candidates/projects/workbench → rebuild `launched.json` → publish Pages → re-push blocklist.
