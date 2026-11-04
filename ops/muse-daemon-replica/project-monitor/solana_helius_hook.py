#!/usr/bin/env python3
"""Helius Solana webhook payload parsing + token-name matching for Pad Hunter.

Used by workbench_api POST /hooks/helius/solana and by smoke tests.
Never logs API keys or webhook secrets.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
TOKEN_WL = BASE / "token_name_watchlist.json"
WATCHLIST = BASE / "watchlist.json"
SOLANA_ALERTS = BASE / "solana_lock_alerts.jsonl"
ONCHAIN_ALERTS = BASE / "onchain_lock_alerts.jsonl"
FACTORIES = BASE / "solana_factories.json"
SECRET_PATH = BASE / ".helius_webhook_secret"
SH = ZoneInfo("Asia/Shanghai")
WRITE_LOCK = threading.Lock()

# Well-known mints to ignore when picking "new" mint
IGNORE_MINTS = {
    "So11111111111111111111111111111111111111112",  # WSOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "USD1ttGY1N17NEEOLmLQ7EwFXipekFr81vFAZoxWoei",  # USD1
}


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def get_webhook_secret() -> str:
    if not SECRET_PATH.exists() or not SECRET_PATH.read_text().strip():
        import os
        import secrets as sec

        SECRET_PATH.write_text(sec.token_urlsafe(32) + "\n")
        os.chmod(SECRET_PATH, 0o600)
    return SECRET_PATH.read_text().strip()


def norm_sym(s: Optional[str]) -> str:
    if not s:
        return ""
    return re.sub(r"[^A-Z0-9]", "", s.strip().lstrip("$").upper())


def norm_name(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.strip().lower()
    return re.sub(r"[\s_\-·•]+", " ", s)


def watched_program_ids() -> set[str]:
    doc = load_json(FACTORIES, {}) or {}
    return {p["program_id"] for p in (doc.get("programs") or []) if p.get("program_id")}


def program_name(pid: str) -> Optional[str]:
    for p in (load_json(FACTORIES, {}) or {}).get("programs") or []:
        if p.get("program_id") == pid:
            return p.get("name") or p.get("id")
    return None


class TokenMatcher:
    def __init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        try:
            from onchain_lock import load_launched_blocklist, hkey
            self.blocked_handles = load_launched_blocklist()
        except Exception:
            self.blocked_handles = set()
            def hkey(h):
                return (h or "").lstrip("@").strip().lower()
            self._hkey = hkey
        else:
            self._hkey = hkey
        self.tokens = load_json(TOKEN_WL, {}) or {}
        raw_by_sym = self.tokens.get("by_symbol") or {}
        self.by_symbol = {}
        for sym, cands in raw_by_sym.items():
            kept = []
            for c in (cands or []):
                if isinstance(c, str):
                    if self._hkey(c) not in self.blocked_handles:
                        kept.append({"handle": c, "project": c, "explicit": False, "ambiguous": False})
                elif isinstance(c, dict) and self._hkey(c.get("handle")) not in self.blocked_handles:
                    kept.append(c)
            if kept:
                self.by_symbol[sym] = kept
        self.ambiguous = set(self.tokens.get("ambiguous_set") or [])
        self.by_name: dict[str, list] = {}
        for p in self.tokens.get("projects") or []:
            if self._hkey(p.get("handle")) in self.blocked_handles:
                continue
            for n in p.get("match_names") or []:
                self.by_name.setdefault(n, []).append(
                    {
                        "project": p.get("project"),
                        "handle": p.get("handle"),
                        "ambiguous_symbols": p.get("ambiguous_symbols") or [],
                    }
                )
        # Solana-hint projects from watchlist (prefer these on soft matches)
        wl = load_json(WATCHLIST, {}) or {}
        self.solana_handles: set[str] = set()
        for p in wl.get("projects") or []:
            chain = f"{p.get('chain') or ''} {p.get('ca_chain') or ''}".lower()
            if "sol" in chain:
                h = (p.get("handle") or "").lstrip("@").lower()
                if h:
                    self.solana_handles.add(h)
        self.loaded_at = now_iso()

    def match(self, name: Optional[str], symbol: Optional[str]) -> list[dict]:
        hits: dict[str, dict] = {}
        sym = norm_sym(symbol)
        nam = norm_name(name)

        if sym and sym in self.by_symbol:
            ambiguous = sym in self.ambiguous or any(
                c.get("ambiguous") for c in self.by_symbol[sym]
            )
            for c in self.by_symbol[sym]:
                key = (c.get("handle") or c.get("project") or "").lower()
                hits[key] = {
                    "project": c.get("project"),
                    "handle": c.get("handle"),
                    "via": f"symbol:{sym}",
                    "explicit": bool(c.get("explicit")),
                    "ambiguous": ambiguous or bool(c.get("ambiguous")),
                }

        if nam and nam in self.by_name:
            for c in self.by_name[nam]:
                key = (c.get("handle") or c.get("project") or "").lower()
                if key in hits:
                    hits[key]["via"] += f"+name:{nam}"
                else:
                    hits[key] = {
                        "project": c.get("project"),
                        "handle": c.get("handle"),
                        "via": f"name:{nam}",
                        "explicit": False,
                        "ambiguous": False,
                    }

        if nam and len(nam) >= 5:
            for nkey, cands in self.by_name.items():
                if len(nkey) < 5:
                    continue
                if nkey in nam or nam in nkey:
                    for c in cands:
                        key = (c.get("handle") or c.get("project") or "").lower()
                        if key not in hits:
                            hits[key] = {
                                "project": c.get("project"),
                                "handle": c.get("handle"),
                                "via": f"name_fuzzy:{nkey}",
                                "explicit": False,
                                "ambiguous": True,
                            }

        out = list(hits.values())
        # Prefer Solana-hint projects when multiple hits
        if len(out) > 1 and self.solana_handles:
            sol = [
                h
                for h in out
                if (h.get("handle") or "").lstrip("@").lower() in self.solana_handles
            ]
            if sol:
                out = sol
        return out


MATCHER = TokenMatcher()
_MATCHER_LOADED = 0.0


def matcher() -> TokenMatcher:
    import time

    global _MATCHER_LOADED
    if time.time() - _MATCHER_LOADED > 60:
        MATCHER.reload()
        _MATCHER_LOADED = time.time()
    return MATCHER


def confidence_for(hit: dict) -> str:
    if hit.get("ambiguous") and not hit.get("explicit"):
        return "low"
    via = hit.get("via") or ""
    if hit.get("explicit") and not hit.get("ambiguous"):
        return "medium"
    if "name:" in via and "fuzzy" not in via:
        return "medium"
    if "fuzzy" in via:
        return "low"
    return "low"


def _collect_mints(tx: dict) -> list[str]:
    mints: list[str] = []
    seen: set[str] = set()

    def add(m: Any) -> None:
        if not isinstance(m, str) or len(m) < 32:
            return
        if m in IGNORE_MINTS or m in seen:
            return
        seen.add(m)
        mints.append(m)

    for t in tx.get("tokenTransfers") or []:
        add(t.get("mint"))
    for ad in tx.get("accountData") or []:
        for ch in ad.get("tokenBalanceChanges") or []:
            add(ch.get("mint"))
    events = tx.get("events") or {}
    if isinstance(events, dict):
        for ev in events.values():
            if isinstance(ev, dict):
                add(ev.get("mint"))
                for nft in ev.get("nfts") or []:
                    if isinstance(nft, dict):
                        add(nft.get("mint"))
            elif isinstance(ev, list):
                for item in ev:
                    if isinstance(item, dict):
                        add(item.get("mint"))
    # raw shape
    meta = tx.get("meta") or {}
    for bal in (meta.get("postTokenBalances") or []) + (meta.get("preTokenBalances") or []):
        add(bal.get("mint"))
    return mints


def _extract_name_symbol(tx: dict) -> tuple[Optional[str], Optional[str]]:
    name = symbol = None
    # Enhanced: some payloads put token metadata under events or description
    for key in ("tokenName", "name", "token_name"):
        v = tx.get(key)
        if isinstance(v, str) and v.strip():
            name = v.strip()
            break
    for key in ("tokenSymbol", "symbol", "token_symbol"):
        v = tx.get(key)
        if isinstance(v, str) and v.strip():
            symbol = v.strip().lstrip("$")
            break
    events = tx.get("events") or {}
    if isinstance(events, dict):
        for ev in events.values():
            if not isinstance(ev, dict):
                continue
            if not name and isinstance(ev.get("name"), str):
                name = ev["name"].strip()
            if not symbol and isinstance(ev.get("symbol"), str):
                symbol = ev["symbol"].strip().lstrip("$")
            # Pump.fun style nested
            tok = ev.get("token") if isinstance(ev.get("token"), dict) else None
            if tok:
                if not name and isinstance(tok.get("name"), str):
                    name = tok["name"].strip()
                if not symbol and isinstance(tok.get("symbol"), str):
                    symbol = tok["symbol"].strip().lstrip("$")
    # Parse "created TOKEN (SYM)" style descriptions loosely
    desc = tx.get("description") or ""
    if isinstance(desc, str) and desc and (not name or not symbol):
        m = re.search(
            r"(?:creat(?:ed|e)|launch(?:ed)?)\s+([A-Za-z0-9][\w .'-]{1,40}?)\s*(?:\(|-|—|/)\s*\$?([A-Z0-9]{2,12})",
            desc,
            re.I,
        )
        if m:
            name = name or m.group(1).strip()
            symbol = symbol or m.group(2).strip()
        else:
            m2 = re.search(r"\$([A-Z0-9]{2,12})\b", desc)
            if m2 and not symbol:
                symbol = m2.group(1)
    return name, symbol


def _involved_programs(tx: dict) -> set[str]:
    found: set[str] = set()
    watched = watched_program_ids()
    # enhanced: accountData accounts
    for ad in tx.get("accountData") or []:
        acc = ad.get("account")
        if isinstance(acc, str) and acc in watched:
            found.add(acc)
    # source field sometimes names programs; also check instructions in raw
    raw = tx.get("transaction") or {}
    msg = raw.get("message") or {}
    keys = msg.get("accountKeys") or []
    # accountKeys may be strings or {pubkey, ...}
    key_strs = []
    for k in keys:
        if isinstance(k, str):
            key_strs.append(k)
        elif isinstance(k, dict) and isinstance(k.get("pubkey"), str):
            key_strs.append(k["pubkey"])
    for k in key_strs:
        if k in watched:
            found.add(k)
    # Also scan any string fields for known program ids (cheap)
    blob = json.dumps(tx, ensure_ascii=False)
    for pid in watched:
        if pid in blob:
            found.add(pid)
    return found


def parse_transactions(payload: Any) -> list[dict]:
    """Normalize Helius body (list or dict) to a list of tx dicts."""
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("transactions"), list):
            return [x for x in payload["transactions"] if isinstance(x, dict)]
        # single tx
        if payload.get("signature") or payload.get("transaction") or payload.get("type"):
            return [payload]
    return []


def process_tx(tx: dict, *, synthetic: bool = False) -> list[dict]:
    """Parse one tx → zero or more alert events (one per mint×project match, or unmatched log)."""
    programs = _involved_programs(tx)
    mints = _collect_mints(tx)
    name, symbol = _extract_name_symbol(tx)
    sig = tx.get("signature") or (
        (tx.get("transaction") or {}).get("signatures") or [None]
    )[0]
    slot = tx.get("slot")
    tx_type = tx.get("type")
    source_prog = None
    if programs:
        # Prefer pump.fun if present
        pump = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
        source_prog = pump if pump in programs else next(iter(programs))
    factory = program_name(source_prog) if source_prog else None

    # No mint → nothing actionable
    if not mints:
        return []

    m = matcher()
    hits = m.match(name, symbol) if (name or symbol) else []
    events: list[dict] = []

    # Prefer first non-ignored mint as primary CA
    primary = mints[0]
    if hits:
        for hit in hits:
            conf = confidence_for(hit)
            # Solana-hint boost for medium soft matches
            h = (hit.get("handle") or "").lstrip("@").lower()
            if conf == "low" and hit.get("explicit") and h in m.solana_handles:
                conf = "medium"
            ev = {
                "type": "ONCHAIN_LOCK",
                "confidence": conf,
                "reason": hit.get("via"),
                "project": hit.get("project"),
                "handle": hit.get("handle"),
                "address": primary,
                "deployer": tx.get("feePayer"),
                "chain": "solana",
                "tx": sig,
                "block": slot,
                "via": hit.get("via"),
                "factory": factory,
                "program_id": source_prog,
                "token_name": name,
                "token_symbol": symbol,
                "source": "helius_solana",
                "tx_type": tx_type,
                "programs": sorted(programs),
                "mints": mints[:8],
                "at": now_iso(),
            }
            if synthetic:
                ev["synthetic"] = True
                ev["note"] = "synthetic smoke test — do not publish"
            events.append(ev)
    else:
        # Log unmatched creates at low confidence only when we have a symbol/name
        # (avoid flooding alerts with every Pump.fun mint)
        if name or symbol:
            ev = {
                "type": "SOLANA_LOCK_UNMATCHED",
                "confidence": "none",
                "reason": "no_watchlist_match",
                "project": None,
                "handle": None,
                "address": primary,
                "deployer": tx.get("feePayer"),
                "chain": "solana",
                "tx": sig,
                "block": slot,
                "factory": factory,
                "program_id": source_prog,
                "token_name": name,
                "token_symbol": symbol,
                "source": "helius_solana",
                "tx_type": tx_type,
                "programs": sorted(programs),
                "mints": mints[:8],
                "at": now_iso(),
            }
            if synthetic:
                ev["synthetic"] = True
                ev["note"] = "synthetic smoke test — do not publish"
            events.append(ev)
    return events


def append_alert_line(path: Path, ev: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def persist_events(events: list[dict]) -> dict:
    """Write to solana_lock_alerts + onchain_lock_alerts (matched only). Rebuild ca_finds on match."""
    matched = 0
    unmatched = 0
    with WRITE_LOCK:
        for ev in events:
            append_alert_line(SOLANA_ALERTS, ev)
            if ev.get("type") == "ONCHAIN_LOCK" and not ev.get("synthetic"):
                # Skip already-launched projects (same blocklist as EVM onchain_lock)
                try:
                    from onchain_lock import load_launched_blocklist, hkey
                    if hkey(ev.get("handle")) in load_launched_blocklist():
                        continue
                except Exception:
                    pass
                append_alert_line(ONCHAIN_ALERTS, ev)
                matched += 1
            elif ev.get("type") == "ONCHAIN_LOCK" and ev.get("synthetic"):
                # still write synthetic only to solana file (already done); skip onchain/ca_finds
                matched += 0
                unmatched += 0
            else:
                unmatched += 1
    rebuilt = False
    real_matches = [
        e
        for e in events
        if e.get("type") == "ONCHAIN_LOCK"
        and not e.get("synthetic")
        and e.get("confidence") in ("low", "medium", "high", "confirmed")
    ]
    if real_matches:
        try:
            subprocess.check_call(
                [str(BASE / ".venv/bin/python"), str(BASE / "build_ca_finds.py")],
                cwd=str(BASE),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=60,
            )
            rebuilt = True
        except Exception:
            rebuilt = False
    return {
        "events": len(events),
        "matched": len(real_matches),
        "unmatched": unmatched,
        "ca_finds_rebuilt": rebuilt,
    }


def process_payload(payload: Any, *, synthetic: bool = False) -> dict:
    """Parse Helius payload. Under workbench_only pref, ignore mass traffic unless
    workbench currently has Solana items (or synthetic smoke tests)."""
    if not synthetic:
        try:
            pref = json.loads((BASE / "solana_scan_pref.json").read_text(encoding="utf-8"))
            mode = (pref.get("mode") or "workbench_only").lower()
        except Exception:
            mode = "workbench_only"
        if mode == "workbench_only":
            try:
                wb = json.loads((BASE / "workbench_active.json").read_text(encoding="utf-8"))
            except Exception:
                wb = {}
            sol = []
            for it in wb.get("items") or []:
                chain = f"{it.get('chain') or ''} {it.get('ca_chain') or ''}".lower()
                if "sol" in chain:
                    sol.append((it.get("handle") or "").lstrip("@"))
            if not sol:
                return {
                    "events": 0, "matched": 0, "unmatched": 0, "transactions": 0,
                    "ca_finds_rebuilt": False, "skipped": "workbench_only_no_solana",
                }
    txs = parse_transactions(payload)
    all_events: list[dict] = []
    for tx in txs:
        all_events.extend(process_tx(tx, synthetic=synthetic))
    stats = persist_events(all_events)
    stats["transactions"] = len(txs)
    return stats
