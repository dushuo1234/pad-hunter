#!/usr/bin/env python3
"""watched_wallets.json — creator / team wallet store (spec 4.7 [C5], fed in P0).

P0 FEEDS this store. P1: onchain_lock Matcher merges active rows by confidence tier;
high + factory → hard evidence toward confirmed; medium/low → candidate only.

Row: {handle, chain, wallet, source, confidence, evidence_url, added_at, expires_at,
      expires_rule, note_zh}
  handle  lowercase, no @
  source  x_official | nft_deployer | docs | testnet | site | ens | scan
  confidence high | medium | low  (never raised by P0 except nft_deployer)
Merge key (handle, chain, wallet_norm). Re-adding keeps the earliest added_at and the
highest confidence; expiry is extended, never shortened.
"""
from __future__ import annotations

import fcntl
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
STORE = BASE / "watched_wallets.json"
SH = ZoneInfo("Asia/Shanghai")
CONF_RANK = {"low": 0, "medium": 1, "high": 2}
DEFAULT_TTL_DAYS = 30
AFTER_LISTING_TTL_DAYS = 7


def _cfg() -> dict:
    try:
        return json.loads((BASE / "launch_config.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def norm_wallet(w: str) -> str:
    w = (w or "").strip()
    return w.lower() if w.lower().startswith("0x") else w


def norm_handle(h) -> str:
    return str(h or "").strip().lstrip("@").lower()


def _parse(ts):
    try:
        return datetime.fromisoformat(str(ts))
    except Exception:
        return None


def expiry_for(added_at: str, listing_at: str | None = None) -> tuple[str, str]:
    cfg = _cfg()
    after = int(cfg.get("watched_wallet_ttl_days_after_listing") or AFTER_LISTING_TTL_DAYS)
    dflt = int(cfg.get("watched_wallet_default_ttl_days") or DEFAULT_TTL_DAYS)
    la = _parse(listing_at)
    if la:
        return (la + timedelta(days=after)).isoformat(timespec="seconds"), f"开盘后{after}天移除"
    aa = _parse(added_at) or datetime.now(SH)
    return (aa + timedelta(days=dflt)).isoformat(timespec="seconds"), f"未知开盘时间，加入后{dflt}天移除"


def classify_source(origins: list[str], sources: list[str]) -> tuple[str, str]:
    """(source, confidence) for a scanned EOA, from its find sources. Conservative:
    official X → medium (only an explicit dev/deployer label would be high; parsed in P1);
    site / JS / HTML / config / scrape → low."""
    blob = " ".join(sources).lower()
    if "x_official" in origins or "x.com/" in blob or "x:@" in blob:
        return "x_official", "medium"
    return "site", "low"


def make_row(*, handle, chain, wallet, source, confidence, evidence_url, added_at, listing_at=None,
             note_zh=None) -> dict:
    exp, rule = expiry_for(added_at, listing_at)
    return {
        "handle": norm_handle(handle),
        "chain": chain,
        "wallet": wallet,
        "source": source,
        "confidence": confidence,
        "evidence_url": evidence_url,
        "added_at": added_at,
        "expires_at": exp,
        "expires_rule": rule,
        "note_zh": note_zh or "扫出的 EOA 钱包，已加入创建者监控（仅监控，不单独锁定）",
    }


def merge(rows: list[dict], new_rows: list[dict]) -> list[dict]:
    idx = {(r["handle"], r.get("chain"), norm_wallet(r["wallet"])): r for r in rows}
    for n in new_rows:
        k = (n["handle"], n.get("chain"), norm_wallet(n["wallet"]))
        cur = idx.get(k)
        if cur is None:
            idx[k] = dict(n)
            continue
        if (n.get("added_at") or "") and (n["added_at"] < (cur.get("added_at") or "9")):
            cur["added_at"] = n["added_at"]
        if CONF_RANK.get(n.get("confidence"), 0) > CONF_RANK.get(cur.get("confidence"), 0):
            cur["confidence"], cur["source"] = n["confidence"], n["source"]
            cur["evidence_url"] = n.get("evidence_url") or cur.get("evidence_url")
        if (n.get("expires_at") or "") > (cur.get("expires_at") or ""):
            cur["expires_at"], cur["expires_rule"] = n["expires_at"], n.get("expires_rule")
    return sorted(idx.values(), key=lambda r: (r["handle"], r.get("chain") or "", norm_wallet(r["wallet"])))


def active(rows: list[dict], now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(SH)
    out = []
    for r in rows:
        e = _parse(r.get("expires_at"))
        if e is None or e > now:
            out.append(r)
    return out


def load(path: Path = STORE) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"schema": "watched_wallets/1", "wallets": []}


def save(rows: list[dict], path: Path = STORE) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    lockp = path.with_suffix(".lock")
    lockp.touch(exist_ok=True)
    with lockp.open("r+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        prev = load(path).get("wallets") or []
        allrows = active(merge(prev, rows))
        doc = {
            "schema": "watched_wallets/1",
            "updated_at": datetime.now(SH).isoformat(timespec="seconds"),
            "note_zh": "创建者/团队钱包监控名单（P1 起用于工厂/新部署匹配，按置信度分层）",
            "count": len(allrows),
            "wallets": allrows,
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(path)
        fcntl.flock(lf, fcntl.LOCK_UN)
    return doc


def index_by_address(rows: list[dict] | None = None, path: Path = STORE) -> dict[str, dict]:
    """addr_lower → best meta row (highest confidence wins). Expired rows excluded."""
    if rows is None:
        rows = active(load(path).get("wallets") or [])
    else:
        rows = active(rows)
    out: dict[str, dict] = {}
    for r in rows:
        a = norm_wallet(r.get("wallet") or "")
        if not a:
            continue
        cur = out.get(a)
        if cur is None or CONF_RANK.get(r.get("confidence"), 0) > CONF_RANK.get(cur.get("confidence"), 0):
            out[a] = r
    return out


def meta_from_watchlists(*, ww_path: Path = STORE, wl_path: Path | None = None) -> dict[str, dict]:
    """Merge watched_wallets.json + wallet_watchlist.json by_address into addr→meta.
    watched_wallets confidence wins on tie-break by CONF_RANK; watchlist-only rows keep
    their stated confidence (often overstated for site scrapes — callers must still
    treat low/medium as soft)."""
    out = index_by_address(path=ww_path)
    wl_path = wl_path or (BASE / "wallet_watchlist.json")
    try:
        wl = json.loads(wl_path.read_text(encoding="utf-8"))
    except Exception:
        wl = {}
    for addr, hits in (wl.get("by_address") or {}).items():
        a = norm_wallet(addr)
        if not a:
            continue
        best = None
        for h in hits or []:
            if isinstance(h, str):
                row = {"handle": norm_handle(h), "wallet": a, "confidence": "medium",
                       "source": "watchlist", "project": h}
            elif isinstance(h, dict):
                row = {
                    "handle": norm_handle(h.get("handle")),
                    "wallet": a,
                    "confidence": (h.get("confidence") or "medium"),
                    "source": h.get("source") or "watchlist",
                    "project": h.get("project"),
                    "chain": h.get("chain"),
                }
            else:
                continue
            if best is None or CONF_RANK.get(row["confidence"], 0) > CONF_RANK.get(best["confidence"], 0):
                best = row
        if best is None:
            continue
        cur = out.get(a)
        if cur is None or CONF_RANK.get(best["confidence"], 0) > CONF_RANK.get(cur.get("confidence"), 0):
            out[a] = best
    return out

