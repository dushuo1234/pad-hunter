#!/usr/bin/env python3
"""Verify CAs harvested from official X posts (x_progress_ca_candidates.json).

Hard rules unchanged: wallets never CA; must pass ca_gate on-chain token verify.
Official-X source → eligible for 已确认 when verified (same as scan_listing_ca lock path).
Writes x_ca_extract_latest.json + appends X_CA lines to fast_site_alerts.jsonl for build_ca_finds.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
CANDS = BASE / "x_progress_ca_candidates.json"
WATCHLIST = BASE / "watchlist.json"
OUT = BASE / "x_ca_extract_latest.json"
ALERTS = BASE / "fast_site_alerts.jsonl"
LAUNCHED = Path("/workspace/push-radar/data/launched.json")
SH = ZoneInfo("Asia/Shanghai")


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def hkey(h: str | None) -> str:
    return (h or "").lower().lstrip("@").strip()


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def launched_handles() -> set[str]:
    la = load(LAUNCHED, {})
    items = la if isinstance(la, list) else la.get("projects") or la.get("items") or []
    return {hkey(i.get("handle")) for i in items if isinstance(i, dict)}


def main() -> int:
    sys.path.insert(0, str(BASE))
    from ca_gate import verify_address

    doc = load(CANDS, {})
    cands = doc.get("candidates") or []
    wl = load(WATCHLIST, {})
    by_h = {hkey(p.get("handle")): p for p in (wl.get("projects") or [])}
    launched = launched_handles()

    verified = []
    rejected = []
    locked = []
    seen = set()

    # Prefer strong_context first
    cands_sorted = sorted(cands, key=lambda c: (not c.get("strong_context"), c.get("type") != "evm"))

    for c in cands_sorted:
        addr = c.get("address") or ""
        handle = hkey(c.get("handle"))
        if not addr or not handle or handle in launched:
            continue
        key = (c.get("type"), addr.lower(), handle)
        if key in seen:
            continue
        seen.add(key)
        proj = by_h.get(handle) or {}
        # skip if project already CA-locked to a different verified CA? still record
        try:
            v = verify_address(addr, chain_hint=proj.get("chain") or proj.get("ca_chain"))
        except TypeError:
            v = verify_address(addr)
        except Exception as e:
            rejected.append({**c, "gate": f"error:{e}"})
            continue
        kind = (v or {}).get("kind") or ""
        note = (v or {}).get("note") or ""
        ok = bool((v or {}).get("is_token"))
        if not ok:
            rejected.append({**c, "gate": v})
            continue

        row = {
            **c,
            "gate": v,
            "verified_at": now_iso(),
            "project": proj.get("name"),
            "confidence": "high" if c.get("strong_context") else "medium",
            "source_label": "官推X",
        }
        verified.append(row)

        # Update watchlist CA if empty or same
        if proj is not None and handle in by_h:
            p = by_h[handle]
            existing = (p.get("ca") or "").lower()
            if not existing or existing == addr.lower():
                p["ca"] = addr
                p["ca_chain"] = (v or {}).get("chain") or p.get("ca_chain") or p.get("chain")
                p["ca_source"] = "x_official"
                p["ca_locked"] = True
                p["ca_verified_at"] = now_iso()
                locked.append({"handle": handle, "address": addr})

        # alert line for build_ca_finds
        ev_url = c.get("evidence_url") or ""
        src = ev_url if ev_url else f"x:@{handle}"
        alert = {
            "type": "X_CA",
            "ts": now_iso(),
            "handle": handle,
            "name": proj.get("name"),
            "address": addr,
            "chain": (v or {}).get("chain") or proj.get("chain"),
            "source": src,
            "evidence_url": ev_url,
            "snippet": c.get("snippet"),
            "kind": "token",
            "label_zh": "合约CA",
            "confidence": "high",
            "gate": {"kind": kind, "note": note, "symbol": (v or {}).get("symbol"), "is_token": True},
            "alert_zh": f"官推X扫到CA {addr[:10]}…（已链上核验）",
        }
        try:
            with ALERTS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(alert, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"WARN alert write: {e}")

    if locked:
        WATCHLIST.write_text(json.dumps(wl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    out = {
        "generated_at": now_iso(),
        "input": len(cands),
        "verified": len(verified),
        "rejected": len(rejected),
        "locked_to_watchlist": locked,
        "finds": verified,
        "rejects_sample": rejected[:30],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"[{now_iso()}] extract_x_ca input={len(cands)} verified={len(verified)} "
        f"rejected={len(rejected)} locked={len(locked)} -> {OUT}"
    )
    for v in verified[:10]:
        print(f"  CA @{v.get('handle')} {v.get('address')} {(v.get('gate') or {}).get('symbol') or ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
