# Pad Hunter workbench — Cloudflare Workers sync

Cloud multi-device sync for pins + reviewed marks (parity with box `workbench_api.py` 1.5.0).

- **Public URL:** `https://api.adualpha.win`
- **Backend:** Worker + Durable Object room `pad-hunter-v5`
- **Auth:** header `X-Pad-Hunter-Token` (same token as box `workbench_api_token.txt`)
- **CORS:** `https://dushuo1234.github.io` + `localhost` / `127.0.0.1`
- **WS:** `wss://api.adualpha.win/v1/workbench/ws?token=…`

## Endpoints

| Method | Path | Notes |
|--------|------|-------|
| GET | `/health` | Public. Reports version + pin count |
| GET | `/v1/workbench/pins` | Auth. `{synced_at,items,removed}` |
| POST | `/v1/workbench/sync` | Auth. LWW merge (+ optional `removed` tombstones) |
| POST | `/v1/workbench/pins/sync` | Alias of `/sync` |
| GET | `/v1/workbench/reviewed` | Auth |
| POST | `/v1/workbench/reviewed/sync` | Auth. LWW on `max(at,cleared_at)` |
| WS | `/v1/workbench/ws` | hello / pins / reviewed / radar / blocklist / launched; sync ops; ping/pong; close 4401 |
| POST | `/v1/launched/mark` | Auth. Manual 已开盘; see 1.7.1-cf |
| GET | `/v1/launched/recent` | Auth. Manual marks for clients + box sync |
| POST | `/v1/workbench/alert` | Auth. 工作台即将开始提醒 `{alerts:[{id,handle,kind,ts,...}], dry_run?}`; dedupe by id; broadcasts WS `workbench_alert` |
| GET | `/v1/workbench/alerts` | Auth. Last 200 提醒; WS hello also sends `workbench_alerts` |

Radar / Helius / poller stay on the box. Local `workbench_api.py` remains as fallback.

## Deploy

```bash
cd /workspace/project-monitor/cf-workbench
npm install
npx wrangler login          # once (browser OAuth)
# set secret from box token file (do not echo):
npx wrangler secret put WORKBENCH_TOKEN < /workspace/project-monitor/workbench_api_token.txt
npx wrangler deploy
```

Custom domain `api.adualpha.win` is declared in `wrangler.toml` (`custom_domain = true`).
Zone `adualpha.win` must already be Active on the same Cloudflare account.

## Re-seed / reset DO state

Delete the Durable Object storage from the dashboard (Workers → pad-hunter-workbench → Durable Objects),
or change `ROOM_NAME` in `wrangler.toml` to mint a fresh room. First boot re-seeds from `seed-pins.json`.

## Update seed from box

```bash
cp /workspace/project-monitor/workbench_active.json seed-pins.json
cp /workspace/project-monitor/workbench_reviewed.json seed-reviewed.json
npx wrangler deploy
```

(Seed only applies when DO storage has no `pins` yet.)

## Current status (2026-10-23 Asia/Shanghai)

- **Live URL:** `https://api.adualpha.win` (Workers Route on zone `adualpha.win`)
- **Fallback:** `https://pad-hunter-workbench.a18675489863.workers.dev`
- Tunnel `pad-hunter` ingress for `api.adualpha.win` cleared (was causing 1033). Old DNS CNAME may still exist; Worker route handles traffic at the edge without needing `custom_domain`.
- Seed pin: GiwaMemeCom. WS broadcast ~30–40ms.

## 1.6.0-cf — launched blocklist (2026-10-23)

- `GET/POST /v1/workbench/blocklist` (token). Body `{handles:[...], mode:"replace"|"add", source}`.
  Stored in the DO; blocked pins are dropped + tombstoned + broadcast (`origin_client_id: box-launched-prune`),
  and any later sync that re-adds a blocked handle is dropped (`dropped_launched`).
- Room is now `pad-hunter-v2` (old room's instance was pinned by a setInterval keepalive and ignored deploys; timer removed).
- Box: `/workspace/project-monitor/cf_workbench_prune.py` pushes the blocklist (removed_launched.json + launched.json),
  tombstones leftovers, and mirrors cloud pins → local `workbench_active.json`.
  Called by `prune_launched.py` (mirror at start, push+mirror at end) and `mark_launched_from_ca.py`. Network errors are non-fatal.

## 1.7.0-cf — realtime radar (Telegram → open tabs)

- `POST /v1/radar/push` (token) — `{client_id, cards|items, mode:"upsert"|"replace_recent", snapshot_meta?}`
- `POST /v1/radar/candidates` — alias of push
- `GET /v1/radar/recent` — token **or** allowed Origin (github.io / localhost); public read of recent cards
- WS `/v1/workbench/ws`: after hello/pins/reviewed also sends `{type:"radar", state:{synced_at,cards,count}}`
- On push: broadcast `{type:"radar",...}` and `{type:"radar_delta", cards:[...]}` (delta if ≤40 cards)
- Rolling store: last 200 cards in DO (`radar` key). Full `candidates.json` stays on Pages.
- Box: `cf_radar_push.py`; hooked from `tg_push_fast.py` after merge `added:` list; daemon seeds newest 50 on start.
- Room: `pad-hunter-v4` (v3 DO stayed awake on old code due to live WS clients).

## 1.7.1-cf — 手动确认已开盘 (2026-10-23)

- `POST /v1/launched/mark` (token) — body `{handle, name?, reason:"manual", at?, client_id?, source?}`
  - Adds handle to durable blocklist, appends `manual_launched` audit (DO storage, last 500)
  - Tombstones matching pins, drops radar cards for that handle
  - WS fanout: `launched_mark`, `blocklist`, `pins` (if hit), `radar` / `radar_delta` (if hit)
  - Response: `{ok, mark, already_blocked, blocklist_count, dropped_launched, pins, launched, radar_removed}`
- `GET /v1/launched/recent` (token) — `{updated_at, count, items:[{handle,name,reason,at,client_id,source}], blocklist_count, handles}`
- `GET /v1/workbench/blocklist` also returns `manual_count` / `manual_updated_at`
- Blocklist `mode:replace` from box **unions** durable manual marks (so prune cannot wipe a fresh site tap)
- WS hello also sends `blocklist` + `launched` state snapshots
- Room: `pad-hunter-v5` (v4 DO stayed awake on old 1.7.0 code due to live WS clients); radar endpoints unchanged
- Box: `sync_manual_launched.py` (+ `_daemon.sh`) polls recent marks → `removed_launched.json` (listing_at=null)
  → prune watchlist/candidates/projects/workbench → rebuild `launched.json` → publish Pages → re-push blocklist

## 1.7.2-cf — unmark + build guard (2026-10-23)

- `POST /v1/launched/unmark` (token) `{handle, client_id?}` → removes the handle from manual marks + blocklist; WS `launched_unmark` + `blocklist`.
  Response `{ok, handle, removed_manual, removed_blocked, blocklist_count, launched}`.
- Room `pad-hunter-v6` (v5 instance was pinned on stale code by live WS clients; seeded from v5 without test handle).
- Build guard: deploy.sh passes `--var BUILD_ID:<epoch>`; Worker forwards `X-PH-Build`; a stale DO closes sockets (1012) and `ctx.abort()`s → next request runs new code. Clients should reconnect on 1012 / retry on 503.
