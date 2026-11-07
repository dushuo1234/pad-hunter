#!/usr/bin/env python3
"""Shared pre-alert check: is a token CA already trading (=> 已开盘, not NEW_CA)?

Uses DexScreener public API (no key):
  GET https://api.dexscreener.com/latest/dex/tokens/{address}
A CA counts as already-launched when it has >=1 pair whose pairCreatedAt is older
than MIN_AGE_HOURS (default 3h) and some liquidity or 24h volume.
Fresh pairs (< MIN_AGE_HOURS) are a genuine new launch -> still alert.

Cached in trading_check_cache.json (10 min TTL) to keep pollers fast.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
CACHE = BASE / "trading_check_cache.json"
SH = ZoneInfo("Asia/Shanghai")
MIN_AGE_HOURS = float(os.environ.get("TRADING_MIN_AGE_HOURS", "3"))
TTL_S = 600
UA = "PadHunterTradingCheck/1.0"


def _load_cache() -> dict:
    try:
        return json.loads(CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(c: dict) -> None:
    try:
        tmp = CACHE.with_suffix(".tmp")
        tmp.write_text(json.dumps(c, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(CACHE)
    except Exception:
        pass


def _fetch(address: str, timeout: int = 10) -> list[dict] | None:
    url = f"https://api.dexscreener.com/latest/dex/tokens/{address}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8", errors="replace") or "{}")
        return d.get("pairs") or []
    except Exception:
        return None


def check_trading(address: str, chain: str | None = None, *, use_cache: bool = True) -> dict:
    """Return {trading, launched_old, first_pair_at, age_hours, liquidity_usd, volume_h24, pairs, chain, dex_url, error}."""
    addr = (address or "").strip()
    key = addr.lower() if addr.startswith("0x") else addr
    now = time.time()
    cache = _load_cache() if use_cache else {}
    hit = cache.get(key)
    if hit and now - hit.get("_ts", 0) < TTL_S:
        return hit
    pairs = _fetch(addr)
    out = {"address": addr, "trading": False, "launched_old": False, "pairs": 0,
           "first_pair_at": None, "age_hours": None, "liquidity_usd": 0.0,
           "volume_h24": 0.0, "chain": chain, "dex_url": None, "error": None}
    if pairs is None:
        out["error"] = "dexscreener_unreachable"
        return out  # don't cache failures
    # only pairs where this address is base/quote token
    rel = []
    for p in pairs:
        b = ((p.get("baseToken") or {}).get("address") or "")
        q = ((p.get("quoteToken") or {}).get("address") or "")
        if key in (b.lower() if addr.startswith("0x") else b, q.lower() if addr.startswith("0x") else q):
            rel.append(p)
    if rel:
        created = [p.get("pairCreatedAt") for p in rel if p.get("pairCreatedAt")]
        first = min(created) / 1000 if created else None
        liq = sum(float((p.get("liquidity") or {}).get("usd") or 0) for p in rel)
        vol = sum(float((p.get("volume") or {}).get("h24") or 0) for p in rel)
        best = max(rel, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
        out.update({
            "pairs": len(rel),
            "trading": (liq > 0 or vol > 0),
            "liquidity_usd": round(liq, 2),
            "volume_h24": round(vol, 2),
            "chain": best.get("chainId") or chain,
            "dex_url": best.get("url"),
            "symbol": (best.get("baseToken") or {}).get("symbol"),
            "name": (best.get("baseToken") or {}).get("name"),
        })
        if first:
            out["first_pair_at"] = datetime.fromtimestamp(first, SH).isoformat(timespec="seconds")
            out["age_hours"] = round((now - first) / 3600, 2)
            out["launched_old"] = bool(out["trading"] and out["age_hours"] >= MIN_AGE_HOURS)
    out["_ts"] = now
    cache[key] = out
    _save_cache(cache)
    return out


if __name__ == "__main__":
    import sys
    print(json.dumps(check_trading(sys.argv[1] if len(sys.argv) > 1 else
                                   "0xaacbc156435dbab7815a61bccba1c827e52a7777"),
                     ensure_ascii=False, indent=2))
