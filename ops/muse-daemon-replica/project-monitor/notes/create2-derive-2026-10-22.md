# CREATE2 salt/initcode derive + Sol harvest + X refresh (2026-10-22)

## Goal
Raise real token-CA yield without relaxing `ca_gate` on-chain ERC20/token verification.

## 1) CREATE2 / factory path (`trace_wallet_ca.py`)

### Shipped
- `create2_address(factory, salt, init_code_hash)` — EIP-1014
- `eip1167_init_code` / hash — OpenZeppelin Clones minimal proxy
- `parse_clone_deterministic_input` / `create2_from_clone_call` — selectors `0xb86b2ceb`, `0xf14188e0`
- `token_from_factory_log` — ABI-aware token field (Clanker/SpinUp/LiquidLaunch topic1; four.meme + Virtuals data word1). **Event token > salt derive.**
- `factory_creates_for_wallet` — prefers ABI token; drops uint256-shaped noise (`0x0000…`); secondary `create2_hits_from_tx_input` on same tx (`via=create2_derive`)
- `create2_from_wallet_recent_txs` — Blockscout eth `filter=from` scan for cloneDeterministic / launchpad `to` (bounded)
- TRACE_CA / `build_trace_finds` carry `via`, `note_zh`, `factory_id`
- `build_ca_finds.py` — TRACE_CA notes include `note_zh`; ingests `SOLANA_TRACE_CA`

### Dry-run numbers
| Check | Result |
|-------|--------|
| Unit: CREATE2 ↔ cloneDeterministic roundtrip | OK |
| Live launchpad logs (~800 blk): tokens ABI-decoded | **9** (clanker_v4_base 4, fourmeme_tm2_bsc 5) |
| factories with logs in window | 2 / 13 launchpad |
| clanker/fourmeme tx input = cloneDeterministic? | **No** (custom sels `0xdf40224a` / `0x519ebb10`) → create2_derive 0 on those txs (expected) |
| Demo: random recent fourmeme deployer matched via `factory_creates_for_wallet` | **1 clean hit**, matched event token, note_zh 含「事件 ABI 代币字段」; before noise filter had 3 (2 false uint-addrs) |
| Watchlist sample `Superboard_` deep-trace | TRACE_CA **0** (referral EOA, no launchpad creates in lookback) |

### Remaining CREATE2 gaps
- Unknown factory ABIs still need salt+initcode from calldata (not only Clones EIP-1167)
- Base/BSC Blockscout API blocked/missing → `create2_from_wallet_recent_txs` eth-only for listing; other chains rely on event+tx.from path
- Clanker/four.meme/Virtuals use custom create selectors — event path covers them; salt derive not needed when TokenCreated fires

## 2) Solana deployer → mint
- Added `harvest_sol_wallets.py` (filters system programs, pure-hex FP, `*pump` mints); wired in `run_listing_onchain_js.sh` before `solana_wallet_mints.py`
- Harvest **0** watchable Sol EOAs after filters (X/JS/watchlist had only system programs, hex noise, or pump mints like pitch `…pump`)
- `solana_wallet_mints` still **wallets_probed=0 hits=0** — ready when a real project EOA appears

## 3) X refresh
- Refreshed **10** priority unlaunched handles into `x_posts_cache` (+19 posts); left ~912/1000 daily budget
- `scan_x_progress`: near_launch=19, already_live=2; `extract_x_ca`: verified=0 (RealHappyBlock Hype Address correctly rejected as wallet)
- Notable progress text (not new CAs): fomdotcapital **presale live**; Giwatools launchpad **live on testnet**; Inktrons404 auction coming; 0utdotfun ready for ignition; lutra_hl GTD gates

## Do-nots honored
- ca_gate unchanged; no invented listing_at; TapeOut watching not revived; no frontend touch

## Files
- `trace_wallet_ca.py` (+ bak `.bak.pre_create2_20261022`)
- `build_ca_finds.py`, `harvest_sol_wallets.py`, `run_listing_onchain_js.sh`
- `solana_wallet_harvest_latest.json`, `notes/_create2_dryrun_scratch.json`
- `fast_site_poll` pid unchanged (still alive) — no restart required for this path
