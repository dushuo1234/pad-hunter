#!/usr/bin/env python3
"""Build token_name_watchlist.json — expected token names/symbols per project.

Sources:
  - Explicit $TICKER from X bios/posts (x_posts_cache, x_listing_posts_cache)
  - Explicit $TICKER from listing_scan_latest snippets / TG project summaries
  - Project name itself + derived abbrev variants (strip spaces, initials, $NAME)
  - Known watchlist names that already look like tickers ($PKC, $NIVRA)

Ambiguous / common symbols are flagged so onchain_lock treats them as low-confidence
name-only matches (need wallet corroboration to promote).

Incremental: previous entries are kept; re-run merges new evidence.
"""
from __future__ import annotations

import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
OUT = BASE / "token_name_watchlist.json"
WATCHLIST = BASE / "watchlist.json"
PROJECTS = Path("/workspace/push-radar/data/projects.json")
SH = ZoneInfo("Asia/Shanghai")

TICKER_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9]{1,14})")
# very common / ambiguous — name-only match stays low unless wallet also hits
AMBIGUOUS = {
    "AI", "BTC", "ETH", "SOL", "BNB", "USDT", "USDC", "USD", "TOKEN", "COIN",
    "NFT", "DAO", "DEX", "DEFI", "MEME", "PEPE", "DOGE", "SHIB", "WETH", "WBTC",
    "INK", "BASE", "OP", "ARB", "MATIC", "AVAX", "TRON", "XRP", "ADA", "DOT",
    "APP", "LAB", "LABS", "FUN", "IO", "GG", "XYZ", "META", "WEB3", "CHAIN",
    "SWAP", "PAD", "LAUNCH", "MINT", "DROP", "GAME", "FI", "网络", "代币",
}


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def norm_sym(s: str) -> str:
    s = (s or "").strip().lstrip("$").upper()
    s = re.sub(r"[^A-Z0-9]", "", s)
    return s


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").strip().lower()
    s = re.sub(r"[\s_\-·•]+", " ", s)
    return s


def derive_variants(project_name: str, handle: str | None) -> list[dict]:
    """Heuristic name/symbol variants from project name / handle."""
    out = []
    name = (project_name or "").strip()
    if not name:
        return out
    # if name is already $TICKER
    if name.startswith("$") and 2 <= len(name) <= 16:
        out.append({"value": name.lstrip("$"), "kind": "symbol", "origin": "project_name_ticker", "explicit": True})
        return out

    cleaned = re.sub(r"[^\w\s]", " ", name, flags=re.UNICODE)
    parts = [p for p in cleaned.split() if p]
    # full name as token name candidate
    out.append({"value": name, "kind": "name", "origin": "project_name", "explicit": False})

    # joined (no spaces): MasterStudios / HappyBlock
    if len(parts) >= 2:
        joined = "".join(parts)
        if 3 <= len(joined) <= 24:
            out.append({"value": joined, "kind": "name", "origin": "name_joined", "explicit": False})
        # initials
        initials = "".join(p[0] for p in parts if p[0].isalnum())
        if 2 <= len(initials) <= 6:
            out.append({"value": initials.upper(), "kind": "symbol", "origin": "name_initials", "explicit": False})
        # first word if looks ticker-ish
        first = parts[0]
        if first.isascii() and first.isalnum() and 3 <= len(first) <= 10:
            out.append({"value": first.upper(), "kind": "symbol", "origin": "name_first_word", "explicit": False})

    # single-token ascii name as symbol
    if len(parts) == 1 and parts[0].isascii() and parts[0].isalnum() and 3 <= len(parts[0]) <= 12:
        out.append({"value": parts[0].upper(), "kind": "symbol", "origin": "name_as_symbol", "explicit": False})

    # handle without digits/underscores trailing
    if handle:
        h = re.sub(r"[^A-Za-z]", "", handle)
        if 3 <= len(h) <= 12 and h.lower() not in {norm_name(name).replace(" ", "")}:
            out.append({"value": h.upper(), "kind": "symbol", "origin": "handle", "explicit": False})
    return out


def build() -> dict:
    wl = load(WATCHLIST, {})
    projects = wl.get("projects") or []
    by_handle = {(p.get("handle") or "").lower(): p for p in projects if p.get("handle")}
    # Also index launched / candidates / push-radar projects so X-cache hits still get a name
    for extra_path in (
        Path("/workspace/push-radar/data/projects.json"),
        Path("/workspace/push-radar/data/candidates.json"),
        Path("/workspace/push-radar/data/launched.json"),
        BASE / "removed_launched.json",
    ):
        raw = load(extra_path, None)
        if raw is None:
            continue
        if isinstance(raw, list):
            items = raw
        elif isinstance(raw, dict):
            items = raw.get("projects") or raw.get("items") or raw.get("candidates") or []
            if isinstance(raw.get("by_handle"), dict):
                for h, p in raw["by_handle"].items():
                    if isinstance(p, dict) and h.lower() not in by_handle:
                        by_handle[h.lower()] = p
        else:
            items = []
        for p0 in items:
            if not isinstance(p0, dict):
                continue
            h = (p0.get("handle") or p0.get("twitter_handle") or "").lstrip("@").lower()
            if h and h not in by_handle:
                by_handle[h] = {
                    "name": p0.get("name") or p0.get("project"),
                    "handle": p0.get("handle") or p0.get("twitter_handle"),
                }

    # Soft-deleted 已开盘 handles must NOT stay in symbol/name indexes (prevents Hatch re-alerts)
    rem = load(BASE / "removed_launched.json", {})
    blocked = {
        (e.get("handle") or "").lstrip("@").lower()
        for e in (rem.get("items") if isinstance(rem, dict) else rem) or []
        if isinstance(e, dict) and not e.get("restored")
    }
    for h in list(by_handle.keys()):
        if h in blocked:
            by_handle.pop(h, None)

    # handle -> list of candidate dicts
    bucket: dict[str, dict] = {}

    def ensure(handle: str | None, name: str | None) -> dict | None:
        h = (handle or "").lstrip("@")
        if not h and not name:
            return None
        key = (h or name or "?").lower()
        if key in blocked or (h and h.lower() in blocked):
            return None
        if key not in bucket:
            proj = by_handle.get(h.lower()) if h else None
            bucket[key] = {
                "project": name or (proj or {}).get("name") or h,
                "handle": h or (proj or {}).get("handle"),
                "symbols": [],  # list of {symbol, sources, explicit, ambiguous}
                "names": [],    # list of {name, sources, explicit}
                "_sym_idx": {},
                "_name_idx": {},
            }
        slot = bucket[key]
        if name and not slot.get("project"):
            slot["project"] = name
        return slot

    def add_symbol(slot: dict, symbol: str, source: str, explicit: bool):
        sym = norm_sym(symbol)
        if not sym or len(sym) < 2 or len(sym) > 16:
            return
        ambiguous = sym in AMBIGUOUS or len(sym) <= 2
        idx = slot["_sym_idx"]
        if sym not in idx:
            entry = {
                "symbol": sym,
                "explicit": explicit,
                "ambiguous": ambiguous,
                "sources": [source],
            }
            slot["symbols"].append(entry)
            idx[sym] = entry
        else:
            e = idx[sym]
            if source not in e["sources"]:
                e["sources"].append(source)
            if explicit:
                e["explicit"] = True
            if ambiguous:
                e["ambiguous"] = True

    def add_name(slot: dict, name: str, source: str, explicit: bool):
        n = (name or "").strip()
        if not n or len(n) < 2:
            return
        key = norm_name(n)
        if not key:
            return
        idx = slot["_name_idx"]
        if key not in idx:
            entry = {"name": n, "name_norm": key, "explicit": explicit, "sources": [source]}
            slot["names"].append(entry)
            idx[key] = entry
        else:
            e = idx[key]
            if source not in e["sources"]:
                e["sources"].append(source)
            if explicit:
                e["explicit"] = True

    # previous
    prev = load(OUT, {})
    for pe in prev.get("projects") or []:
        slot = ensure(pe.get("handle"), pe.get("project"))
        if not slot:
            continue
        for s in pe.get("symbols") or []:
            add_symbol(slot, s.get("symbol") or "", f"previous:{','.join((s.get('sources') or [])[:1])}", bool(s.get("explicit")))
        for n in pe.get("names") or []:
            add_name(slot, n.get("name") or "", f"previous:{','.join((n.get('sources') or [])[:1])}", bool(n.get("explicit")))

    # watchlist projects — always derive variants
    for p in projects:
        slot = ensure(p.get("handle"), p.get("name"))
        if not slot:
            continue
        for v in derive_variants(p.get("name") or "", p.get("handle")):
            if v["kind"] == "symbol":
                add_symbol(slot, v["value"], v["origin"], v["explicit"])
            else:
                add_name(slot, v["value"], v["origin"], v["explicit"])

    # X caches — explicit $TICKER
    for cache_name in ("x_posts_cache.json", "x_listing_posts_cache.json"):
        xc = load(BASE / cache_name, {})
        for handle, u in (xc.get("users") or {}).items():
            blob = json.dumps(u, ensure_ascii=False) if isinstance(u, dict) else str(u)
            tickers = TICKER_RE.findall(blob)
            if not tickers:
                continue
            proj = by_handle.get(handle.lower())
            slot = ensure(handle, (proj or {}).get("name"))
            if not slot:
                continue
            for t in tickers:
                add_symbol(slot, t, f"x_cache:{cache_name}", True)

    # listing_scan snippets
    ls = load(BASE / "listing_scan_latest.json", {})
    for r in ls.get("results") or []:
        blob = json.dumps(r, ensure_ascii=False)
        tickers = TICKER_RE.findall(blob)
        if not tickers:
            continue
        slot = ensure(r.get("handle"), r.get("name"))
        if not slot:
            continue
        for t in tickers:
            add_symbol(slot, t, "listing_scan", True)

    # TG project summaries
    raw = load(PROJECTS, [])
    items = raw if isinstance(raw, list) else (raw.get("projects") or [])
    for it in items:
        handle = it.get("twitter_handle") or it.get("handle")
        blob = " ".join(
            str(it.get(k) or "")
            for k in ("name", "summary_cn", "summary_en", "status", "listing")
        )
        tickers = TICKER_RE.findall(blob)
        # also name starting with $
        slot = ensure(handle, it.get("name"))
        if not slot:
            continue
        for t in tickers:
            add_symbol(slot, t, "tg_projects", True)
        if (it.get("name") or "").startswith("$"):
            add_symbol(slot, it["name"], "tg_project_name", True)

    # finalize — drop index helpers, sort
    projects_out = []
    for slot in bucket.values():
        slot.pop("_sym_idx", None)
        slot.pop("_name_idx", None)
        # prefer explicit symbols first
        slot["symbols"].sort(key=lambda s: (not s.get("explicit"), s.get("ambiguous", False), s["symbol"]))
        slot["names"].sort(key=lambda n: (not n.get("explicit"), n.get("name_norm") or ""))
        # compact matching indexes for onchain_lock
        slot["match_symbols"] = [s["symbol"] for s in slot["symbols"]]
        slot["match_names"] = [n["name_norm"] for n in slot["names"]]
        slot["ambiguous_symbols"] = [s["symbol"] for s in slot["symbols"] if s.get("ambiguous")]
        projects_out.append(slot)

    projects_out.sort(key=lambda p: (p.get("handle") or "").lower())

    # reverse index: symbol -> projects
    by_symbol: dict[str, list] = {}
    for p in projects_out:
        for s in p.get("symbols") or []:
            by_symbol.setdefault(s["symbol"], []).append({
                "project": p.get("project"),
                "handle": p.get("handle"),
                "explicit": s.get("explicit"),
                "ambiguous": s.get("ambiguous"),
            })

    return {
        "generated_at": now_iso(),
        "timezone": "Asia/Shanghai",
        "project_count": len(projects_out),
        "projects_with_explicit_ticker": sum(
            1 for p in projects_out if any(s.get("explicit") for s in p.get("symbols") or [])
        ),
        "symbol_count": sum(len(p.get("symbols") or []) for p in projects_out),
        "projects": projects_out,
        "by_symbol": by_symbol,
        "ambiguous_set": sorted(AMBIGUOUS),
        "notes": [
            "explicit=True means $TICKER seen in X/TG/site text.",
            "ambiguous symbols alone => low confidence; need wallet lock to promote.",
            "onchain_lock.py matches ERC20 symbol()/name() against match_symbols / match_names.",
        ],
    }


def write(doc: dict) -> Path:
    tmp = OUT.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(OUT)
    return OUT


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mirror", action="store_true")
    args = ap.parse_args()
    doc = build()
    write(doc)
    print(
        f"token_name_watchlist: projects={doc['project_count']} "
        f"with_explicit_ticker={doc['projects_with_explicit_ticker']} "
        f"symbols={doc['symbol_count']} -> {OUT}"
    )
    if args.mirror:
        for dest in (
            Path("/workspace/publish-pages-data/token_name_watchlist.json"),
            Path("/cursor/stores/store-b953e26e-8884-4159-b9a8-d2e6295761c8/publish-pages-data/token_name_watchlist.json"),
        ):
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                print(f"  mirrored -> {dest}")
            except Exception as e:
                print(f"  mirror fail {dest}: {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
