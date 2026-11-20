#!/usr/bin/env python3
"""Harvest project-owned Solana EOAs into wallet_watchlist for solana_wallet_mints.

Sources: x_posts_cache, x_listing_posts_cache, ca_finds, js_factory_scan, watchlist fields,
listing_scan, fast_site_alerts. Filters system programs, pump.fun mints (*pump), pure-hex
false positives. Does NOT invent addresses. Merges into wallet_watchlist.json (chain=solana).
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
WATCH = BASE / "wallet_watchlist.json"
OUT_HARVEST = BASE / "solana_wallet_harvest_latest.json"
SH = ZoneInfo("Asia/Shanghai")
B58 = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")
HEXISH = re.compile(r"^[0-9a-fA-Fx]+$")
IGNORE = {
    "So11111111111111111111111111111111111111112",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    "11111111111111111111111111111111",
    "SysvarRent111111111111111111111111111111111",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL",
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",
    "ComputeBudget111111111111111111111111111111",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # pump.fun program
    "metaqbxxUerdq28cj1RbAWkYQm3ybzjb6a8bt518x1s",
}


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def looks_sol_eoa(addr: str) -> bool:
    """Heuristic: base58 32–44, not system, not pure hex, not pump.fun mint suffix."""
    if not addr or addr.startswith("0x"):
        return False
    if len(addr) < 32 or len(addr) > 44:
        return False
    if addr in IGNORE:
        return False
    if not B58.fullmatch(addr):
        return False
    if HEXISH.match(addr):
        return False
    # pump.fun mint addresses commonly end with "pump" — those are mints, not deployers
    if addr.endswith("pump"):
        return False
    return True


def collect() -> list[dict]:
    wl = load(BASE / "watchlist.json", {})
    by_h = {(p.get("handle") or "").lower(): p for p in (wl.get("projects") or []) if p.get("handle")}
    found: dict[str, dict] = {}

    def add(addr, handle, name, source, note=None):
        if not looks_sol_eoa(addr):
            return
        # Prefer Solana-tagged projects; still keep if handle known
        proj = by_h.get((handle or "").lower()) or {}
        chain = (proj.get("chain") or "").lower()
        inferred = " ".join(proj.get("inferred_chains") or []).lower()
        solish = "sol" in chain or "sol" in inferred or not proj
        if proj and not solish and "sol" not in (note or "").lower():
            # Non-sol project — only keep if source explicitly sol-tagged
            if "sol" not in source.lower():
                return
        key = addr  # case-sensitive for Sol
        cur = found.get(key)
        entry = {
            "address": addr,
            "handle": handle or proj.get("handle"),
            "name": name or proj.get("name"),
            "source": source,
            "note": note or "harvested Solana-looking address (verify EOA vs mint)",
            "chain": "solana",
            "confidence": "medium",
        }
        if cur is None:
            found[key] = entry
        else:
            if source not in (cur.get("sources") or []):
                cur.setdefault("sources", [cur.get("source")]).append(source)

    # watchlist free-text + fields
    for p in wl.get("projects") or []:
        for fld in ("ca", "ca_alt", "mint", "deployer", "wallet", "team_wallet"):
            v = p.get(fld)
            vals = v if isinstance(v, list) else [v]
            for x in vals:
                if isinstance(x, str):
                    # mint field is usually a mint, not EOA — skip *pump; others medium
                    if fld == "mint" and str(x).endswith("pump"):
                        continue
                    if fld == "mint":
                        continue  # mints are not wallets
                    add(x.strip(), p.get("handle"), p.get("name"), f"watchlist.{fld}")
        blob = " ".join(str(p.get(k) or "") for k in ("summary_en", "summary_cn", "listing_signal", "note", "notes"))
        for m in B58.findall(blob):
            add(m, p.get("handle"), p.get("name"), "watchlist_text")

    # X caches
    for cache_name in ("x_posts_cache.json", "x_listing_posts_cache.json"):
        xc = load(BASE / cache_name, {})
        users = xc.get("users") or {}
        # listing cache may be {handle: [posts]}
        if cache_name.endswith("listing_posts_cache.json") and not users and isinstance(xc, dict):
            for handle, posts in xc.items():
                if handle in ("fetched_at", "note", "missing_handles") or not isinstance(posts, list):
                    continue
                for p in posts:
                    if not isinstance(p, dict):
                        continue
                    for m in B58.findall(p.get("text") or ""):
                        add(m, handle, None, f"x_listing:{handle}", note="from listing X post")
            continue
        for handle, u in users.items():
            if not isinstance(u, dict):
                continue
            for p in u.get("posts") or []:
                if not isinstance(p, dict):
                    continue
                for m in B58.findall(p.get("text") or ""):
                    add(m, handle, None, f"x_cache:{handle}", note="from official X post text")
            bio = u.get("description") or u.get("bio") or ""
            for m in B58.findall(bio):
                add(m, handle, None, f"x_bio:{handle}")

    # ca_finds solana-looking
    cf = load(BASE / "ca_finds.json", {})
    for f in cf.get("finds") or []:
        addr = (f.get("address") or "").strip()
        if looks_sol_eoa(addr) and (f.get("kind") or "") == "wallet":
            add(addr, f.get("handle"), f.get("project") or f.get("name"),
                f"ca_finds:{f.get('source')}", note=f.get("note"))

    # js scan — only non-hex base58 in address lists / raw blobs for sol projects
    js = load(BASE / "js_factory_scan_latest.json", {})
    for r in js.get("results") or []:
        handle = r.get("handle")
        name = r.get("name")
        proj = by_h.get((handle or "").lower()) or {}
        chain = ((proj.get("chain") or r.get("chain") or "") + "").lower()
        if "sol" not in chain and "sol" not in " ".join(proj.get("inferred_chains") or []).lower():
            continue
        blob = json.dumps(r, ensure_ascii=False)
        for m in B58.findall(blob):
            add(m, handle, name, "js_factory_scan")

    return list(found.values())


def merge_into_watchlist(harvested: list[dict]) -> dict:
    doc = load(WATCH, {})
    wallets = list(doc.get("wallets") or [])
    by_addr = dict(doc.get("by_address") or {})
    existing = {(w.get("address") or "") for w in wallets}
    added = 0
    for h in harvested:
        addr = h["address"]
        if addr in existing:
            continue
        row = {
            "address": addr,
            "address_norm": addr,  # sol case-sensitive; keep as-is
            "chain": "solana",
            "confidence": h.get("confidence") or "medium",
            "sources": [h.get("source") or "sol_harvest"],
            "note": h.get("note"),
            "evidence_url": f"https://x.com/{h['handle']}" if h.get("handle") else None,
            "first_seen": now_iso(),
            "last_seen": now_iso(),
            "project": h.get("name"),
            "handle": h.get("handle"),
            "kind_hint": "sol_eoa_candidate",
        }
        wallets.append(row)
        by_addr.setdefault(addr, []).append({
            "project": h.get("name"), "handle": h.get("handle"),
            "confidence": row["confidence"], "chain": "solana",
        })
        existing.add(addr)
        added += 1
    doc["wallets"] = wallets
    doc["by_address"] = by_addr
    doc["wallet_count"] = len(wallets)
    doc["solana_harvest_at"] = now_iso()
    doc["solana_harvest_added"] = added
    # preserve projects grouping lightly: append sol-only project slots
    projects = list(doc.get("projects") or [])
    by_h = {(p.get("handle") or "").lower(): p for p in projects}
    for h in harvested:
        hk = (h.get("handle") or "").lower()
        if not hk:
            continue
        slot = by_h.get(hk)
        if slot is None:
            slot = {"project": h.get("name"), "handle": h.get("handle"), "chain": "solana", "wallets": []}
            projects.append(slot)
            by_h[hk] = slot
        addrs = {w.get("address") for w in slot.get("wallets") or []}
        if h["address"] not in addrs:
            slot.setdefault("wallets", []).append({
                "address": h["address"], "address_norm": h["address"],
                "chain": "solana", "confidence": "medium",
                "sources": [h.get("source")], "note": h.get("note"),
                "first_seen": now_iso(), "last_seen": now_iso(),
            })
    doc["projects"] = projects
    doc["project_count"] = len(projects)
    tmp = WATCH.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(WATCH)
    return {"added": added, "harvested": len(harvested), "wallet_count": len(wallets)}


def main() -> int:
    harvested = collect()
    # classify: keep only candidates that are NOT obvious mints (already filtered *pump)
    summary = {
        "generated_at": now_iso(),
        "harvested": len(harvested),
        "results": harvested,
        "notes": [
            "Filtered system programs, pure-hex false positives, and *pump mints.",
            "Remaining are Solana-looking addresses from project X/JS/watchlist — verify EOA before trusting.",
            "solana_wallet_mints.py probes these via getSignaturesForAddress.",
        ],
    }
    OUT_HARVEST.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    merge = merge_into_watchlist(harvested)
    print(f"[{now_iso()}] sol harvest={len(harvested)} added_to_watchlist={merge['added']} "
          f"wallets_now={merge['wallet_count']} -> {OUT_HARVEST}")
    for h in harvested[:15]:
        print(f"  {h['address'][:12]}… @{h.get('handle')} via {h.get('source')}")
    if not harvested:
        print("  (zero watchable Sol EOAs after filters — documented)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
