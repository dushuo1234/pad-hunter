# PACK_MANIFEST — Pad Hunter → Muse daemon pack (2026-11-04)

## ⚠ FULL archive CONTAINS SECRETS — treat as confidential

Do **not** commit `pad-hunter-daemons-FULL-20261104.tar.gz` to a public git repo.
Hand only to Muse / adu secure channel. Prefer delete local copies after Muse confirms vault + unpack.

## Archives

| File | Role | Approx compressed | Approx unpacked | Members |
|---|---|---|---|---|
| `pad-hunter-daemons-FULL-20261104.tar.gz` | **Runnable** tree: code + state snapshots + **live secrets/sessions** | ~17.5 MB | ~110 MB | 1024 |
| `pad-hunter-daemons-src-20261104.tar.gz` | Code-only / sanitized twin (no tokens, no `.session`, no `.env`) | ~17.5 MB | ~110 MB | 1000 |

**Priority for Muse:** use the **FULL** pack.

## Top-level layout (both packs)

```
project-monitor/     # daemons, scripts, cf-workbench, docs, notes, JSON state
push-radar/          # static site bits + current data/*.json (no bak dumps)
tg-monitor-code/     # Telethon/scripts (+ secrets only in FULL)
```

## Included (code & state)

- All `*_daemon.sh` present on box at pack time (13)
- `workbench_api.py`, scan/build/publish/merge/prune scripts, `run_listing_onchain_js.sh`, today_* scripts
- `cf-workbench/` (src, wrangler.toml, seeds, deploy.sh) — without `node_modules`
- READMEs, `docs/`, `notes/`
- Non-secret state snapshots: `watchlist.json`, `ca_finds.json`, `workbench_active.json`, `workbench_reviewed.json`, `fast_site_state.json`, `today_projects.json`, `today_projects_boost.json`
- `push-radar/` README/index/assets + current data JSONs (candidates/projects/today/launched/…; skipped bak_* and duplicate large ca_finds with NOTE)
- `tg-monitor-code/`: `*.py`, targets, `projects.json`, `MIGRATED_TO_HK.md`
- FULL only: live secrets listed in `SECRET_KEYS.md` (original relative paths under `project-monitor/` and `tg-monitor-code/`)
- FULL also keeps `sniper_config.redacted.json` alongside live `sniper_config.json`

## Excluded from both packs (bulk / non-essential)

- `alerts/`, `*.log`, `*.pid`, `__pycache__/`, `.venv/` / `venv/`, `node_modules/`, `.git/`
- `bin/` (cloudflared/ngrok binaries — reinstall on Muse)
- Large historical dumps: `_before_*`, `_baseline_run_*`, `_routine_baseline_*`, `routine_baselines/`, `replay/`, staging dirs (`e1_*`, `p0_staging`, `p1_staging`, `split_staging`, `publicnode_staging`)
- Heavy caches: `x_posts_cache.json*`, large `*.jsonl` event tapes, `x_inbox*`
- push-radar `*.bak*` dumps; tg-monitor `venv/`, projects.json.bak*

## SRC pack additionally excludes (sanitized)

- `.secrets/`, `secrets/`, `workbench_api_token.txt`, `*.env` / `.env`, `ngrok_authtoken.txt`
- `.helius_*`, `.etherscan_api_key`, `.publicnode_*`
- Live `sniper_config.json` (only `sniper_config.redacted.json`)
- `tg.session`, `.env`, `login_state.json`

## FULL pack secret-presence check (passed)

- `project-monitor/.secrets/github_token` — present
- `project-monitor/workbench_api_token.txt` — present
- `project-monitor/.helius_api_key` — present
- `project-monitor/sniper_config.json` — present
- `tg-monitor-code/tg.session` — present
- `tg-monitor-code/.env` — present
- Also present: etherscan/publicnode keys, 6551 + telegram bot tokens, cloudflare tunnel tokens, ngrok authtoken, login_state.json, today_ca_speed.env

## SRC pack exclusion check (passed)

- No paths matching live `workbench_api_token`, `.session`, `.secrets/`, `.env`, `github_token`, helius/etherscan/publicnode secret files, or live `sniper_config.json`

## Unpack hint for Muse

```bash
mkdir -p /workspace && cd /workspace
tar -xzf pad-hunter-daemons-FULL-20261104.tar.gz
# expect project-monitor/, push-radar/, tg-monitor-code/
chmod 600 project-monitor/workbench_api_token.txt \
  project-monitor/.secrets/* project-monitor/secrets/* \
  project-monitor/.helius_* project-monitor/.etherscan_api_key \
  project-monitor/.publicnode_* project-monitor/ngrok_authtoken.txt \
  tg-monitor-code/.env tg-monitor-code/tg.session
# Follow shadow → cutover protocol in notes/muse-daemon-replica-checklist-2026-11-04.md
# Do NOT dual-publish with box.
```

## Pack produced by

Ori executor on box, 2026-11-04 (Asia/Shanghai), per adu option-2 + secrets-included override.
