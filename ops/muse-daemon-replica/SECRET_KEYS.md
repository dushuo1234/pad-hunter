# SECRET_KEYS — Muse vault / pack inventory (names & paths only)

> **CONFIDENTIAL.** Values are inside `pad-hunter-daemons-FULL-20261104.tar.gz` at the relative paths below.
> Do **not** paste values into chat, public git, or issues. Rotate if this archive is shared beyond Muse.

## Included in FULL pack (paths relative to archive root)

| Path in pack | Used by | Purpose |
|---|---|---|
| `project-monitor/.secrets/github_token` | `publish_pages_file.py`, `publish_ca_finds_*` | GitHub PAT for Contents API → Pages `public/data/*` |
| Env alternates: `GITHUB_TOKEN` / `GH_TOKEN` / `PAD_HUNTER_GH_TOKEN` | same | Override file token |
| Env: `PAD_HUNTER_GH_TOKEN_FILE` | `publish_pages_file.py` | Alternate path to GH token file |
| `project-monitor/workbench_api_token.txt` | `workbench_api.py`, `cf_radar_push.py`, `sync_manual_launched.py`, `cf_workbench_prune.py`, `today_*` / `workbench_soon_*` watchers, `cf-workbench/deploy.sh` | Local FastAPI auth (`X-Pad-Hunter-Token`); source for CF Worker secret `WORKBENCH_TOKEN` |
| Env: `PAD_HUNTER_WORKBENCH_TOKEN_NEW` | today/workbench soon scripts | Override workbench token without file |
| CF Worker secret name: `WORKBENCH_TOKEN` | `cf-workbench` Worker | Same value as workbench_api_token.txt after `wrangler secret put` |
| `project-monitor/.secrets/cloudflare_tunnel_token.txt` | tunnel helpers / docs | Cloudflare tunnel token (alternate form) |
| `project-monitor/.secrets/cloudflare_tunnel_token_raw.txt` | `cloudflared_daemon.sh` | Raw tunnel token loaded into `TUNNEL_TOKEN` |
| `project-monitor/ngrok_authtoken.txt` | `workbench_api_daemon.sh` (optional) | ngrok authtoken if `TUNNEL_PROVIDER=ngrok` |
| `project-monitor/.helius_api_key` | `ca_gate.py`, `first_buy.py`, `solana_helius_setup.py`, `solana_wallet_mints.py` | Helius Solana RPC / enhanced txs |
| Env: `HELIUS_API_KEY` | `solana_helius_setup.py`, `first_buy.py` | Override `.helius_api_key` |
| `project-monitor/.helius_webhook_secret` | `workbench_api.py` (webhook auth), `solana_helius_setup.py`, `solana_helius_hook.py` | Helius webhook verify / setup |
| `project-monitor/.etherscan_api_key` | `funding_links.py`, `today_deployer_hunt.py`, `rpc_funding` path | Etherscan V2 API key |
| Env: `ETHERSCAN_API_KEY` / `ETHERSCAN_API_KEY_V2` | `funding_links.py` | Override file key |
| `project-monitor/.publicnode_token` | `rpc_funding.py` | Allnodes/PublicNode personal token |
| `project-monitor/.publicnode_rpc_urls` | `rpc_funding.py`, publish secret-file guard | Per-chain RPC URLs that embed personal token paths |
| Env: `PADHUNTER_PUBLICNODE_BASE` / `PADHUNTER_PUBLICNODE_BSC` (etc.) | `rpc_funding.py` | Per-chain PublicNode URL overrides |
| `project-monitor/secrets/6551_token` (also `.secrets/6551_token`) | `sniper_6551.py`, `x6551.py` | 6551 / OpenNews Bearer for X/AI API |
| Env: `SNIPER_6551_TOKEN` / `OPENNEWS_TOKEN` / `OPENTWITTER_API_KEY` / `X6551_TOKEN` | same | Override 6551 token |
| `project-monitor/sniper_config.json` | `sniper_buy.py` / sniper tooling | Live sniper settings incl. `token_6551` field (also present as `sniper_config.redacted.json` with values wiped) |
| `project-monitor/secrets/telegram_bot_token` (also `.secrets/`) | `telegram_today_only.py`, `today_projects_tg_push.py` | Telegram Bot API token (@aduahhbot) |
| `project-monitor/secrets/telegram_today_chat.json` (also `.secrets/`) | same | Today-push chat_id / scope config |
| `project-monitor/today_ca_speed.env` | `today_t20_watch_daemon.sh`, `today_deployer_hunt_daemon.sh` | Timing knobs (sourced by daemons; no API secrets, but `.env` pattern) |
| `tg-monitor-code/.env` | Telethon login / `fetch_and_classify.py` stack | Keys: `TG_API_ID`, `TG_API_HASH`, `TG_PHONE`, `TG_PROXY_*` |
| `tg-monitor-code/tg.session` | Telethon | Session blob ≡ logged-in TG user (treat as password) |
| `tg-monitor-code/login_state.json` | login_phase* scripts | Intermediate login state (`phone_code_hash`, flags) |

## Not duplicated as separate files (but related)

- Cursor Routines stay on Ori; they are not secrets.
- BAW / wallet private keys for live buys: **not** in this pack (sniper stays dry_run policy unless Ori says otherwise).
- CF account API tokens beyond tunnel + WORKBENCH_TOKEN: use existing wrangler login on Muse if needed.

## Muse vault checklist

Enter each row into Muse secure storage, then unpack FULL archive preserving paths under the Muse VM workdir (e.g. mirror `/workspace/project-monitor` and a tg-monitor dir). chmod 600 on all token/session files after unpack.
