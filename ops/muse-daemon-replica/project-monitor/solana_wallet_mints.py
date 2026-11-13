#!/usr/bin/env python3
"""Light Solana deployer→mint probe via Helius/public RPC (no paid DAS required).

For each Solana-looking address in wallet_watchlist / ca_finds (kind=wallet):
  - getSignaturesForAddress (recent)
  - getTransaction; look for newly created SPL mint accounts in meta
Writes solana_wallet_mints_latest.json + SOLANA_TRACE_CA lines to solana_lock_alerts.jsonl.
Does NOT bypass ca_gate — build_ca_finds / extract still verify mint ownership.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
WATCH = BASE / "wallet_watchlist.json"
CA_FINDS = BASE / "ca_finds.json"
OUT = BASE / "solana_wallet_mints_latest.json"
ALERTS = BASE / "solana_lock_alerts.jsonl"
KEY_FILE = BASE / ".helius_api_key"
SH = ZoneInfo("Asia/Shanghai")
B58 = __import__("re").compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
IGNORE = {
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
}


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def rpc_url() -> str:
    key = ""
    try:
        key = KEY_FILE.read_text().strip()
    except Exception:
        pass
    if key:
        return f"https://mainnet.helius-rpc.com/?api-key={key}"
    return "https://api.mainnet-beta.solana.com"


def rpc(method: str, params: list, timeout: int = 25):
    url = rpc_url()
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    # never print URL (contains key)
    try:
        out = subprocess.run(
            ["curl", "-sS", "-X", "POST", "-H", "Content-Type: application/json",
             "--max-time", str(timeout), "-d", body, url],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if out.returncode != 0:
            return None
        return json.loads(out.stdout)
    except Exception:
        return None


def collect_wallets(limit: int = 40) -> list[dict]:
    out = []
    seen = set()
    wl = load(WATCH, {})
    # by_address map or list
    items = []
    if isinstance(wl, dict):
        ba = wl.get("by_address") or {}
        if isinstance(ba, dict):
            for addr, meta in ba.items():
                items.append({"address": addr, **(meta if isinstance(meta, dict) else {})})
        for w in wl.get("wallets") or wl.get("items") or []:
            if isinstance(w, dict):
                items.append(w)
    for it in items:
        addr = (it.get("address") or it.get("wallet") or "").strip()
        if not addr or not B58.match(addr) or addr in IGNORE:
            continue
        if addr.startswith("0x"):
            continue
        if len(addr) < 32:
            continue
        if addr in seen:
            continue
        seen.add(addr)
        out.append({"address": addr, "handle": it.get("handle"), "name": it.get("name") or it.get("label")})
        if len(out) >= limit:
            break
    # also wallets from ca_finds
    cf = load(CA_FINDS, {})
    for f in cf.get("finds") or []:
        if (f.get("kind") or "") != "wallet":
            continue
        addr = (f.get("address") or "").strip()
        if not addr or addr.startswith("0x") or not B58.match(addr) or addr in seen or addr in IGNORE:
            continue
        seen.add(addr)
        out.append({"address": addr, "handle": f.get("handle"), "name": f.get("name")})
        if len(out) >= limit:
            break
    return out


def mints_from_tx(tx: dict) -> list[str]:
    """Heuristic: newly created token-program accounts that look like mints."""
    meta = (tx.get("meta") or {})
    msg = (tx.get("transaction") or {}).get("message") or {}
    account_keys = []
    for k in msg.get("accountKeys") or []:
        if isinstance(k, str):
            account_keys.append(k)
        elif isinstance(k, dict):
            account_keys.append(k.get("pubkey") or "")
    pre = {a.get("mint") for a in (meta.get("preTokenBalances") or []) if a.get("mint")}
    post = []
    for a in meta.get("postTokenBalances") or []:
        m = a.get("mint")
        if m and m not in pre and m not in IGNORE:
            post.append(m)
    # Also check inner instructions for InitializeMint (best-effort via log messages)
    logs = meta.get("logMessages") or []
    for line in logs:
        if "InitializeMint" in line or "initialize mint" in line.lower():
            # can't always parse mint from log; rely on postTokenBalances
            pass
    return list(dict.fromkeys(post))


def probe_wallet(w: dict, sig_limit: int = 15) -> list[dict]:
    addr = w["address"]
    res = rpc("getSignaturesForAddress", [addr, {"limit": sig_limit}])
    if not res or not res.get("result"):
        return []
    found = []
    for sigrow in res["result"][:sig_limit]:
        sig = sigrow.get("signature")
        if not sig:
            continue
        txr = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0}])
        if not txr or not txr.get("result"):
            continue
        for mint in mints_from_tx(txr["result"]):
            found.append({
                "wallet": addr,
                "mint": mint,
                "signature": sig,
                "handle": w.get("handle"),
                "name": w.get("name"),
                "evidence_url": f"https://solscan.io/tx/{sig}",
            })
        time.sleep(0.05)
    return found


def main() -> int:
    wallets = collect_wallets(limit=25)
    all_hits = []
    for w in wallets:
        try:
            hits = probe_wallet(w)
            all_hits.extend(hits)
        except Exception as e:
            print(f"WARN {w.get('address')[:8]}: {e}")
        time.sleep(0.1)
    # dedupe
    seen = set()
    uniq = []
    for h in all_hits:
        k = (h["mint"], h["wallet"])
        if k in seen:
            continue
        seen.add(k)
        uniq.append(h)
        try:
            with ALERTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "type": "SOLANA_TRACE_CA",
                    "ts": now_iso(),
                    "address": h["mint"],
                    "traced_from": h["wallet"],
                    "handle": h.get("handle"),
                    "name": h.get("name"),
                    "evidence_url": h.get("evidence_url"),
                    "chain": "solana",
                    "source": "solana_wallet_mints",
                    "note": "wallet recent tx showed new SPL mint (needs ca_gate)",
                }, ensure_ascii=False) + "\n")
        except Exception:
            pass

    doc = {
        "generated_at": now_iso(),
        "wallets_probed": len(wallets),
        "hits": len(uniq),
        "results": uniq,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[{now_iso()}] solana_wallet_mints wallets={len(wallets)} hits={len(uniq)} -> {OUT}")
    for h in uniq[:10]:
        print(f"  {h['mint'][:12]}… from {h['wallet'][:8]}… @{h.get('handle')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
