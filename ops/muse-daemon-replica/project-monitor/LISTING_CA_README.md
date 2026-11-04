# Pad Hunter — Listing / CA early-warning

## Files
- `watchlist.json` — locked projects (name, handle, sites, ca, listing_signal, inferred_chains)
- `scan_listing_ca.py` — TG raw_text + site HTML + optional `x_posts_cache.json`
- `scan_onchain.py` — public RPC `eth_getCode` / `eth_getLogs` on known factories
- `factories.json` — chain RPCs, factory addresses, per-project chain hints
- `x_posts_cache.json` — bios/posts from X MCP (refresh before scan when possible)
- `listing_scan_latest.json` / `onchain_scan_latest.json` — last run outputs

## Suggested cadence (parent creates routine)
1. Every **15–30 min** (Asia/Shanghai daytime): refresh X cache for priority handles (`$PKC`, minting, `即将启动`), run `scan_listing_ca.py`.
2. Every **30–60 min**: run `scan_onchain.py` for RH + HyperEVM factory log windows.
3. Alert only on `NEW_CA` / `LISTING_SIGNAL` / `NEW_DEPLOY` diffs vs previous.

## X cache refresh (executor / parent with MCP)
```
get_users_by_usernames → write bios into x_posts_cache.json
get_users_posts(id) for priority → append posts
```
Script never invents API tokens.

## On-chain approach
Prefer **event logs** from factories (PairCreated / launch-gate creates / pool inits) over bytecode dumps.
`eth_getCode` is used only to confirm the factory is live (byte size). Verified source: open explorer URL when Cloudflare allows; no Etherscan key in this environment.


### CREATE2 / factory (2026-10-22)
- `trace_wallet_ca.py`: ABI token from launchpad events + OZ `cloneDeterministic` CREATE2 (`via=create2_derive`). See `notes/create2-derive-2026-10-22.md`.
- `harvest_sol_wallets.py` → `solana_wallet_mints.py` (0 Sol EOAs until projects publish wallets).

## Gaps
See `onchain_scan_latest.json` → `gaps`. Private pads (QuantumPad), bio-only CA ($PKC), non-EVM (Ordinals/Kaspa), and unknown Elysium/GIWA factories are called out explicitly.

## JS ↔ factory match (full watchlist)

- `scan_js_factory_match.py` — fetch each usable official site, download same-origin/CDN JS bundles, extract addresses, fingerprint, match vs `onchain_scan_*.json` factory deploys within ±24h (scan-time window).
- Outputs: `js_factory_scan_latest.json` / `js_factory_scan_previous.json`, append-only `js_factory_events.jsonl`.
- Alert types: `NEW_JS_CA`, `JS_FACTORY_MATCH`, `SITE_JS_CHANGE`.

### Routine order
```bash
# or: bash /workspace/project-monitor/run_listing_onchain_js.sh
python3 /workspace/project-monitor/scan_listing_ca.py
python3 /workspace/project-monitor/scan_onchain.py
python3 /workspace/project-monitor/scan_js_factory_match.py
python3 /workspace/project-monitor/trace_wallet_ca.py
python3 /workspace/project-monitor/build_ca_finds.py
```
Alert only on `NEW_JS_CA` / `JS_FACTORY_MATCH` / `SITE_JS_CHANGE` (and existing listing/onchain types).
Treat Ballast addresses as launchpad feed (other tokens), not Ballast's own CA.
`SITE_JS_CHANGE` fires when the address set changes, or when scripts change *and* a non-ambient factory deploy is in the ±24h window.

### Limits
Skips X/Telegram/linktree/truncated URLs; Cloudflare/SPA runtime configs may hide CAs; ambient UniV2 matches flagged `ambient=true`.

### Enrichment (2026-10-22) — more code extraction + discrimination
- `scan_js_factory_match.py` now also pulls addresses from:
  - keyed config (`tokenAddress` / `FACTORY` / `MARKET` / `deployer` …)
  - `const NAME = '0x…'` with CA-ish names
  - explorer `/address/0x` links
  - same-origin config sidecars (`/contracts.json`, `/config.json`, …; HTML soft-404s rejected)
  - optional same-origin sourcemap `sourcesContent`
- Each address gets `extract_method`, `signal_tags`, `signal_confidence`, `signal_note_zh` (third-party feed / referral noise tagged **low**, never bypasses `ca_gate`).
- Per-project `js_completion` / `contract_code_completion` / `game_code_completion` heuristics (≥0.8 = high) → `merge_site_completion.py` writes them into `candidates.json` for 「即将开盘」.
- `trace_wallet_ca.py` adds launchpad **factory tx.from** matching (CREATE2/factory path) for deep traces; classic CREATE derive unchanged. CREATE2 salt derivation still **not** done.
- `ca_gate.verify_address` adds `note_zh` (Chinese UI note); English `note` kept for logs.


## Fast site poller (near-realtime, Sentinel-style)

Lightweight always-on layer so we do not wait for the 30m JS batch:

- `fast_site_poll.py` (v2, concurrent) — one worker thread per usable official site, every **1s** (env `FAST_SITE_INTERVAL` / `--interval`, clamp 1–60). Conditional GET (If-None-Match / If-Modified-Since → 304) else stable HTML fingerprint (external script list, ignoring /cdn-cgi/). Per-host gate ≤1 req/s; 429/503 → automatic host backoff (15s doubling to 300s, honours Retry-After, logged as `[backoff]`, visible in state `backoff`); network errors → per-site backoff up to 60s. On change → full HTML+JS extract via `scan_js_factory_match.scan_one_project` (max 3 concurrent, ≥15s per site; pages whose light fingerprint flaps without a JS change get an escalating cooldown up to 600s). Summary line every 10s with per-site interval p50/p90/max. Old sequential version: `fast_site_poll.v1_sequential.py.bak`.
- `build_ca_finds.py` — aggregates every observed CA into `ca_finds.json` (+ mirror `/workspace/push-radar/data/ca_finds.json`) from fast_site_alerts NEW_JS_CA, js_factory_events NEW_JS_CA, js_factory_scan_latest addresses, listing_scan_latest CAs and watchlist ca/ca_alt/mint. Dedupe (handle, address). Baola/Ballast = confidence low. Run by the daemon on every NEW_JS_CA and at the end of `run_listing_onchain_js.sh`.
- `fast_site_poll_daemon.sh` — start/stop/status (nohup + pidfile).
- State: `fast_site_state.json` (per-site validators + last addresses + alerted set).
- Alerts: append-only `fast_site_alerts.jsonl` (`SITE_CHANGE`, `NEW_JS_CA`, Asia/Shanghai timestamps).
- Wake hint for parent: `fast_site_wake.json` (updated when an alert is appended).

### Start / stop
```bash
# default 15s
bash /workspace/project-monitor/fast_site_poll_daemon.sh start
bash /workspace/project-monitor/fast_site_poll_daemon.sh status
bash /workspace/project-monitor/fast_site_poll_daemon.sh stop

# custom interval
FAST_SITE_INTERVAL=1 bash /workspace/project-monitor/fast_site_poll_daemon.sh start

# one-shot (no daemon)
python3 /workspace/project-monitor/fast_site_poll.py --once --interval 1
```

### Behaviour notes
- Skips X-only / t.me / linktree / truncated `…` URLs (same `is_usable_site` as the batch scanner).
- Light fingerprint prefers ETag / Last-Modified; else a **stable HTML fp** (script `src` list + shell without inline script bodies) to avoid SPA/CDN body churn.
- `SITE_CHANGE` only fires when the full JS/address fingerprint actually moved after extract; `NEW_JS_CA` still deduped per project.

- First sighting baselines addresses **without** flooding `NEW_JS_CA`; later new addresses alert.
- Dedup: same `type:address` for a project is not re-alerted (`alerted_addrs` in state).
- Baola / Ballast-style feed sites: alerts still fire but `confidence=low` (third-party token icons).
- Does **not** replace `run_listing_onchain_js.sh`; factory match stays on the 30m path.


## Wallet → CA trace

When a scraped address is an EOA (wallet) rather than a token contract, we classify it and try to find contracts it **deployed**.

- `trace_wallet_ca.py` — for each EVM address in `ca_finds.json`:
  1. `eth_getCode` on hinted chain (else ethereum → robinhood → hyperevm). `bytes>0` → `kind=contract`; `bytes==0` → `kind=wallet`.
  2. For wallets: public Blockscout (eth.blockscout.com) tx / created_contract + `eth_getTransactionReceipt`; optional short recent-block scan (`--recent-window`, default 800) for medium+/wallet-noted finds when explorer is empty.
  3. Writes `wallet_trace_latest.json`, appends `WALLET_CLASSIFIED` / `CONTRACT_CLASSIFIED` / `TRACE_CA` to `wallet_trace_events.jsonl`.
- `build_ca_finds.py` keeps the original wallet row (`kind=wallet`) and adds TRACE_CA rows (`kind=contract`, `traced_from=<wallet>`, evidence = explorer tx URL).
- Hooked in `run_listing_onchain_js.sh` after the JS scan (warn-only on failure). Live: `fast_site_poll` queues a non-blocking one-shot on each `NEW_JS_CA` EVM address.

### Re-run
```bash
python3 /workspace/project-monitor/trace_wallet_ca.py --recent-window 800
python3 /workspace/project-monitor/build_ca_finds.py
# one address:
python3 /workspace/project-monitor/trace_wallet_ca.py --address 0x… --recent-window 400
```

### Limits (v1)
- **Solana skipped** — no free mint-creation index without API keys.
- Robinhood / HyperEVM explorers: RPC-only (Blockscout CF-blocked / no API wired).
- Does not invent CAs; TRACE_CA only when a deploy tx / receipt `contractAddress` is confirmed.
- Empty-nonce wallets (never sent a tx on that chain) produce classification only, no TRACE_CA.
- Classic **CREATE** deploys are found by deriving `address(keccak(rlp([wallet,nonce])))` for nonce `0..N-1` and checking `eth_getCode` (needs local `.venv` pycryptodome). **CREATE2 / factory-created** tokens are not covered in v1.
- `--force-recent` enables an expensive recent-block receipt scan (off by default).

## 开盘时间 extraction (`extract_listing_times.py`)

- Sources: watchlist fields, TG card text (`projects.jsonl` summary/risk), `listing_scan_latest.json` snippets, `x_posts_cache.json` bios/posts, `x_listing_posts_cache.json` (X recent search from watchlist handles, launch keywords, since 10-10), plus a light homepage re-fetch for 即将启动/mint进行中 projects without a time (≤40 sites).
- Parses: ISO `2026-10-20 14:00 UTC`, `Oct 21 · 06:00 UTC`, `OCTOBER 21st⏰ 19:00 CEST`, `20 October, at 9 PM UTC`, `Mint Date: Oct 22`, `10月27日 13:00`, 今晚/明天/后天, tonight/tomorrow (resolved against the **post time** in the clock's own zone), `in ~2 hours`, `Mainnet Nov 1st`. All converted to Asia/Shanghai. Pure "soon/this week/即将开盘" → no time.
- Output `listing_times.json` (+ mirror `push-radar/data/listing_times.json`): items with `listing_at`, `listing_at_display` (ISO or **未知**), raw, source, evidence_url, confidence, `already_listed`, `within_next_3_days` (now ≤ t ≤ now+3d and not listed), plus a top-level `within_next_3_days` list.
- **Sticky / fill-forward**: a found `listing_at` is never wiped by a later empty scan; replaced only by clearly better evidence (higher confidence, or same-day more precise clock). Projects with nothing found get `listing_at=null`, `listing_at_display="未知"`. The card `listing` field (未开盘/不明/已开盘) stays separate.
- Merged into `watchlist.json` and `push-radar/data/candidates.json` (`listing_at`, `listing_at_source`, `listing_at_raw`, `listing_at_confidence`, `listing_at_evidence_url`, `listing_at_display`, `already_listed`, `within_next_3_days`).
- Refresh `x_listing_posts_cache.json` via X MCP `search_posts_all` with `(from:a OR from:b …) (launch OR TGE OR mint OR UTC OR 开盘 …)` in ≤1000-char batches (25 posts per page).

## Auto-prune launched projects (`prune_launched.py`)

- Launched = (A) token-live wording on the project's own X/site ("$CROPZ is LIVE … CA", "live on Uniswap v4. CA …", 已开盘/开始交易) **plus** an own CA in the same text or a high-confidence contract in `ca_finds.json`; (B) live platforms/feeds (`PLATFORM_LIVE`: Baola/bao.la, Ballast/ballast.exchange); (C) listing_times already_listed with explicit 已开盘/trading wording + CA. Mint-live / claim-live / product-live and CA-only do **not** count (listed under `borderline_kept`).
- Soft delete → `removed_launched.json` (reason, evidence, evidence_url, removed_at, full snapshot). The handles there are a **blocklist** applied every run to `watchlist.json`, `workbench_active.json`, `push-radar/data/candidates.json` and `push-radar/data/projects.json`; `/home/box/.tg-monitor/sync_site.py` also filters it after copying the TG snapshot (backup: `sync_site.py.bak.pre_blocklist`). Any future candidates rebuild must run `prune_launched.py` afterwards (the routine does).
- `push-radar/data/launched.json` (site 「已开盘」 section) is regenerated every run from `removed_launched.json` (dedupe by handle, newest first); `listing_at` = time of the evidence post when known.
- `fast_site_poll.py` reloads watchlist targets every 60s, so removed sites stop polling without a restart.
- `build_ca_finds.py` puts finds of blocklisted handles into `launched_history` (kept) instead of active `finds`.
- Restore: set `"restored": true` on the entry and put `snapshot` back into watchlist (and projects/candidates).

### Routine order (updated)
`scan_listing_ca → extract_listing_times → scan_x_progress → extract_x_ca → scan_onchain → scan_js_factory_match → trace_wallet_ca → solana_wallet_mints → prune_launched → mark_launched_from_ca → build_ca_finds → merge_site_completion` (`run_listing_onchain_js.sh`; new steps are warn-only).

## Workbench realtime API (Sentinel-style, workbench-only) — added 2026-10-20

- `workbench_api.py` (FastAPI, `.venv`) on `127.0.0.1:8780`. Auth header `X-Pad-Hunter-Token` = `workbench_api_token.txt` (local, chmod 600, never commit). `/health` is public (no secrets).
  CORS: `https://dushuo1234.github.io`, `http(s)://localhost|127.0.0.1:*`, `null`. Allowed headers: `X-Pad-Hunter-Token`, `Content-Type`, `ngrok-skip-browser-warning`.
  - `GET /health` → ok, version, workbench_count, poller_alive, poller_target_mode
  - `POST /v1/workbench/sync` `{items:[{handle,name?,sites?,x_url?,chain?,notes?,push?}],client_id?}` → writes `workbench_active.json` (dedupe by handle, full replace)
  - `GET /v1/workbench/status` → per item: url, site_status, last_check_at, last_latency_ms, interval_s, change_count, address_count, last_addresses(≤5), push, listing_at|"未知", checking
  - `POST /v1/workbench/check` `{handle}` → appends `workbench_check_queue.jsonl`; poller drains within ~0.5s and runs a full HTML+JS extract
  - `GET /v1/workbench/detail?handle=` → recent_changes (≤30, state + fast_site_alerts.jsonl), crawl_history (≤100 per-probe), addresses, ca_finds
- `fast_site_poll.py` target mode (`WORKBENCH_ONLY`, default `auto`): once `workbench_active.json` exists, the 1s realtime loop polls ONLY workbench sites (empty workbench ⇒ idle); file absent ⇒ full watchlist (old behaviour). `0` forces full, `1` forces workbench. Reloads within 0.5s of a sync. Per-site `history`, `recent_changes`, `change_count`, `last_latency_ms` live in `fast_site_state.json`.
  The 30-min listing/onchain/js pipeline (`run_listing_onchain_js.sh`) still scans the FULL watchlist.
- `workbench_api_daemon.sh start|stop|restart|status|ensure|url` — API + tunnel + watchdog (every 20s; restarts dead API/tunnel; restarts tunnel after 6 failed public /health checks past a 150s grace).
  Tunnel provider: `ngrok` when `ngrok_authtoken.txt` exists (optional `ngrok_domain.txt` = free static domain ⇒ stable URL), else none (local-only). `TUNNEL_PROVIDER=cloudflared` is available but BLOCKED from this box (egress drops port 7844; only TLS:443 passes). Random tunnel URLs change on restart; current URL in `workbench_api_public_url.txt`, history in `workbench_api_public_url.history`. Frontend should send `ngrok-skip-browser-warning: 1`.


## Official X progress → 「即将开盘」 (`scan_x_progress.py`) — 2026-10-22

- Refresh `x_posts_cache.json` via X MCP (`get_users_posts` / `get_users_by_usernames`; rate limits apply). Helper: `ingest_x_posts.py`.
- Each routine run (`run_listing_onchain_js.sh`) calls `scan_x_progress.py` after `extract_listing_times.py`.
- Classifies recent official posts (≤14d when dated):
  - **already_live** → `x_progress_bucket=already_live` (prune/mark_launched owns 已开盘; never invents `listing_at`)
  - **near_launch** → set `status=即将启动` (if not mint进行中/已开盘), `listing_signal=官推进度·即将开盘…`, `x_launch_readiness=high` (source x)
  - **building** → readiness medium; ≥2 stacked hits can promote 开发中→即将启动
- Frontend PR #31 already includes status 「即将启动」 in 即将开盘 — no new frontend PR required.
- Same pass harvests CA-like strings → `x_progress_ca_candidates.json`; `extract_x_ca.py` runs `ca_gate.verify_address` (wallets/NFTs rejected) and emits `X_CA` into `fast_site_alerts.jsonl` for `build_ca_finds` (official_x provenance when evidence URL is the project’s own post).

### Re-run
```bash
# after refreshing X cache:
python3 /workspace/project-monitor/scan_x_progress.py
python3 /workspace/project-monitor/extract_x_ca.py
python3 /workspace/project-monitor/build_ca_finds.py
python3 /workspace/project-monitor/publish_pages_file.py /workspace/push-radar/data/candidates.json public/data/candidates.json
```

## CA finding next steps (2026-10-22)

Shipped today (on top of JS enrichment):
- Deeper X text CA harvest + `ca_gate` verify + `X_CA` → `build_ca_finds` (official_x).
- `solana_wallet_mints.py` — watched Solana wallet recent txs → new SPL mint heuristic (Helius RPC). Currently **0 Solana EOAs** in `wallet_watchlist` / ca_finds wallets; path is wired for when JS/X adds them.

Still open:
- CREATE2 salt+initcode derivation
- Many sites still have no static CA (X-only announce) — keep refreshing X
- Sparse Solana deployer indexing without more watched Sol mints/wallets
- Huge vendor JS chunks still gated


## TapeRobot / TapeOut immediate CA watch (2026-10-21)
- Config: `tapeout_watch_wallets.json` (9 BSC EOAs, label 「扫出钱包·TapeOut监控」, never CAs). Mirrored as `wallet_watchlist.json.tapeout_watch` (NOT in by_address, so onchain_lock won't force_launch/mislabel).
- Daemon: `tapeout_watch_daemon.sh start|stop|restart|status|ensure` → `tapeout_watch.py --interval 2` (log `tapeout_watch.log`, status `tapeout_watch_status.json`, state `tapeout_watch_state.json`).
  Sources: TapeOut factory create logs (topic 0x2e8868f1…; topic1=processor, topic2=transistors, topic3=creator), four.meme TokenCreate, nonce bump → CREATE address of watched wallets. Alert if creator watched OR name/symbol ~ TapeRobot/ROBOT. All TapeOut creates logged to `tapeout_factory_events.jsonl`.
- X: `tapeout_x_ingest.py <x get_users_posts output file>` for @TapeRobot_bsc (user id 3114058692, since_id in `tapeout_x_state.json`). Needs a routine (daemon can't call x MCP).
- Push: `tapeout_push.push_candidate` — file-locked dedupe by address (`tapeout_seen.json`, first source wins, later ones → also_seen_by; seeded known transistor/processor re-alert once only as 「官方推特确认」 from X). ca_gate: ERC20 → 合约CA, ERC-1155 → 晶体管合约, factory ERC721 → TapeOut Processor; wallets rejected (`tapeout_rejects.jsonl`).
  Writes TAPEOUT_CA (dedupe_key TAPEOUT_CA:<addr>, alert_zh) to `tapeout_ca_alerts.jsonl` + `fast_site_alerts.jsonl` + `onchain_lock_alerts.jsonl`, updates `fast_site_wake.json`, then build_ca_finds + publish_ca_finds_pages (main public/data + gh-pages data/).

### Boost window (T-10 → launch + post, or mint_live)
Config: `tapeout_watch_wallets.json` → `boost` + `boost_targets[]`.
- **Normal:** factory/wallets every **8s**; X wake every **300s**.
- **Boost** (listing_at−10min through listing_at+120min, OR `mint_live:true`): factory/wallets every **2s**; X wake every **45s**.
- Live status: `tapeout_boost_status.json`. X due flag: `tapeout_x_boost_wake.json` (`due:true` + instruction for parent routine / 官网秒级CA快报).
- TapeRobot_bsc listing_at 2026-10-21T16:00+08; mint_live=true → boost already on.
