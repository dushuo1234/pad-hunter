# X progress → 即将开盘 + CA sharpening (2026-10-22)

## A — X progress
- Added `scan_x_progress.py`, `ingest_x_posts.py`; wired into `run_listing_onchain_js.sh`.
- Refreshed ~12 priority official accounts’ recent posts into `x_posts_cache.json` (rate-limited; more can be filled next routine).
- Sample run: **near_launch=20**, **already_live=2** (paperbird_lol trading live; lamp_sol launching right now), **开发中→即将启动** earlier in session for QernApp / KaspaRocket (net 即将启动 59→61 on candidates).
- Notable near-launch from fresh X: thebuidlr (almost live), TapeFoundry (public launch soon), TapeCat_ (打新), play_blastoff (presale whitelist), monarchyfi (gates open soon), ZeromemeFun (countdown), PrivateKeyCoin_ (stand by / CA in bio).
- Published `candidates.json` to main + `public/data/` (commits around 7cc3827 / 09bafde).

## B — CA finding
- `extract_x_ca.py` + `build_ca_finds` accepts `X_CA` with official_x provenance. Harvested 8 CA-like strings from X caches; most already in launched set; 1 live reject correctly classified as wallet (RealHappyBlock Hype Address).
- `solana_wallet_mints.py` wired; **0 Solana wallets** currently in watchlist/finds → 0 hits. Ready when JS/X adds Sol EOAs.
- Did **not** relax ca_gate. TapeRobot not revived.

## Gaps / next
- Keep refreshing X posts for remaining ~100 priority handles (1000/day budget).
- CREATE2 salt derivation; Solana deployer index once wallets exist.
- Parent: ping user that 即将开盘 now also grows from 官推进度; sample new near-launch names; lamp_sol / paperbird may need launched prune on next full scan.
