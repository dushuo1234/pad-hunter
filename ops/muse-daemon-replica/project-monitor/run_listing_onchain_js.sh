#!/usr/bin/env bash
# Routine entry (post-split): onchain → JS/factory → wallet→CA → prune → aggregate.
# Listing-time / listing-signal site crawl lives in listing_scan_daemon.py
# (listing_scan_latest.json + listing_times.json). This pipeline only READs those
# files; extract_listing_times stays as a cheap sticky refresh from the latest scan.
set -euo pipefail
cd /workspace/project-monitor
# NOTE: scan_listing_ca.py removed — owned by listing_scan_daemon (parallel fetches).
# Structured 开盘时间 (sticky fill-forward; never wipes a found listing_at); never fails the routine
python3 extract_listing_times.py || echo "WARN: extract_listing_times.py failed"
# Official X progress → 即将开盘 (+ CA harvest for verify); never fails the routine
python3 scan_x_progress.py || echo "WARN: scan_x_progress.py failed"
python3 extract_x_ca.py || echo "WARN: extract_x_ca.py failed"
python3 scan_onchain.py
python3 scan_js_factory_match.py
# Wallet EOA classify + deploy trace (CREATE + launchpad factory tx.from); never fails the routine
python3 trace_wallet_ca.py --recent-window 0 || echo "WARN: trace_wallet_ca.py failed"
# Solana watched-wallet → recent SPL mint heuristic (Helius/public RPC); warn-only
# Harvest Solana EOAs from X/JS/watchlist into wallet_watchlist (warn-only)
python3 harvest_sol_wallets.py || echo "WARN: harvest_sol_wallets.py failed"
python3 solana_wallet_mints.py || echo "WARN: solana_wallet_mints.py failed"
# Soft-remove launched projects (blocklist) + push-radar/data/launched.json; never fails the routine
python3 prune_launched.py || echo "WARN: prune_launched.py failed"
# CA-locked / already-trading → 已开盘 (also strips workbench); never fails the routine
python3 mark_launched_from_ca.py || echo "WARN: mark_launched_from_ca.py failed"
# ca_finds.json (+ mirror); launched projects go to launched_history; never fails the routine
python3 build_ca_finds.py || echo "WARN: build_ca_finds.py failed"
# Merge JS/site completion heuristics into candidates for 「即将开盘」; never fails the routine
python3 merge_site_completion.py || echo "WARN: merge_site_completion.py failed"

# Rebuild Pages monitor timeline from latest scans (warn-only)
python3 publish_monitor_events.py || echo "WARN: publish_monitor_events.py failed"
