# JS / code CA enrichment (2026-10-22)

## Why
Official sites rarely embed token CAs; previous JS scan only caught ~5/51 projects with addresses (~10 unique). Wallet TRACE_CA often 0 (empty nonce / CREATE2/factory gap).

## Changes
- `scan_js_factory_match.py`: keyed/const/explorer/config extraction; config sidecars; optional sourcemaps; sparse same-origin bundles; signal_tags + Chinese notes; completion heuristics; expanded EVM_DENY (Multicall3, OP predeploys, ambient DEX factories, Anvil keys).
- `trace_wallet_ca.py`: launchpad factory `eth_getLogs` + `tx.from` match (CREATE2/factory path); onchain_scan hint reuse. CREATE2 salt derivation still not done.
- `ca_gate.py`: `note_zh` for UI.
- `build_ca_finds.py`: Chinese low-confidence / referral / icon notes; pass signal notes from JS events.
- `merge_site_completion.py` + `run_listing_onchain_js.sh`: write `js_completion` / `contract_code_completion` / `game_code_completion` into candidates.
- `LISTING_CA_README.md` updated.
- Restarted `fast_site_poll` only (pid refreshed) so live path loads new extract.

## Sample dry-run (10 sites vs previous latest)
- Addresses: **9 → 18** (paperbird exchange/executor, kilnpad contracts, 0-0.city tribute, TapeFoundry MARKET/FACTORY, …)
- Superboard `?ref=` correctly **low** / 推荐链接
- Accumulate OP Stack / UniV4 PoolManager noise filtered

## Gaps remaining
- Many sites still have **no** CA in static JS (X-only announce).
- Solana deployer→mint index still missing without paid API.
- CREATE2 salt+initcode derivation not implemented.
- Sparse extract capped; huge vendor chunks still gated by CA_CONTEXT_JS.
- Completion fields need a full `run_listing_onchain_js.sh` / JS scan pass before 「即将开盘」 fills up.

## Parent
No frontend PR required (PR #31 already reads completion fields). Next routine run picks up batch path; optional: tell user enrichment is live + sample delta.
