#!/usr/bin/env python3
"""Push 今日项目清单 + CA events to api.adualpha.win /v1/today/cas for local bots.

Every CA event carries `chain` (and `chain_note` / wallet note) so bots can label the wallet.
Sources: today_projects.json, alerts/today_t20*.jsonl, today_deployer_hunt_alerts.jsonl,
         ca_locks / ca_finds if present.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE = Path(__file__).resolve().parent
TODAY = BASE / "today_projects.json"
TOKEN_FILE = BASE / "workbench_api_token.txt"
API = os.environ.get("PAD_HUNTER_CF_API", "https://api.adualpha.win").rstrip("/")
UA = "pad-hunter-today-ca-push/1.0"
ALERT_FILES = [
    BASE / "alerts" / "today_deployer_hunt_alerts.jsonl",
    BASE / "alerts" / "today_t20_alerts.jsonl",
    BASE / "alerts" / "today_t20_highconf.jsonl",
    BASE / "alerts" / "workbench_soon.jsonl",
]
LOCKS = BASE / "alerts" / "ca_locks.json"
FINDS = BASE / "alerts" / "ca_finds.json"


def iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def token() -> str:
    t = os.environ.get("PAD_HUNTER_WORKBENCH_TOKEN_NEW", "").strip()
    if not t and TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text().strip()
    return t


def norm_h(h: Any) -> str:
    return str(h or "").strip().lstrip("@").lower()


def norm_chain(c: Any) -> str | None:
    if c is None:
        return None
    s = str(c).strip()
    if not s or s in ("未知", "unknown", "Unknown", "N/A", "-"):
        return None
    low = s.lower().replace(" ", "")
    aliases = {
        "bsc": "BSC",
        "bnb": "BSC",
        "binance": "BSC",
        "binancesmartchain": "BSC",
        "eth": "ETH",
        "ethereum": "ETH",
        "base": "Base",
        "sol": "Solana",
        "solana": "Solana",
        "robinhood": "robinhood",
        "robin": "robinhood",
        "arb": "Arbitrum",
        "arbitrum": "Arbitrum",
        "op": "Optimism",
        "optimism": "Optimism",
        "polygon": "Polygon",
        "matic": "Polygon",
        "avax": "Avalanche",
        "avalanche": "Avalanche",
    }
    return aliases.get(low, s)


def is_real_ca(ca: str | None, source: str | None = None) -> bool:
    s = (ca or "").strip()
    if len(s) < 20:
        return False
    low = s.lower()
    if low.startswith("0x") and len(set(low[2:])) <= 2:  # 0xaaa… / 0x000…
        return False
    if "inject" in str(source or "").lower():
        return False
    return True


def chain_note(chain: str | None, ca: str | None = None) -> str:
    ch = norm_chain(chain) or "unknown"
    ca_s = (ca or "").strip()
    if ca_s:
        return f"[{ch}] {ca_s}"
    return f"[{ch}]"


def load_today() -> list[dict]:
    if not TODAY.exists():
        return []
    doc = json.loads(TODAY.read_text(encoding="utf-8"))
    items = doc.get("items") or doc.get("projects") or []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        h = it.get("handle")
        if not h:
            continue
        ch = norm_chain(it.get("chain"))
        out.append(
            {
                "handle": h,
                "name": it.get("name"),
                "chain": ch,
                "chain_note": f"链:{ch}" if ch else "链:unknown",
                "listing_at": it.get("listing_at"),
                "listing_at_display": it.get("listing_at_display"),
                "site": it.get("site"),
                "tweet_url": it.get("tweet_url"),
                "status": it.get("status"),
                "category": it.get("category"),
                "hours_to_launch": it.get("hours_to_launch"),
            }
        )
    return out


def event_id(handle: str, ca: str, source: str, ts: str) -> str:
    raw = f"{norm_h(handle)}|{(ca or '').lower()}|{source}|{ts[:19]}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def from_alert_line(rec: dict, today_handles: set[str]) -> dict | None:
    h = rec.get("handle") or ""
    if norm_h(h) not in today_handles:
        return None
    ca = (rec.get("ca") or rec.get("address") or "").strip()
    src0 = str(rec.get("source") or rec.get("client_tag") or rec.get("kind") or "alert")
    if not is_real_ca(ca, src0):
        return None
    # skip pure workbench soon without ca
    kind = str(rec.get("kind") or "")
    if kind and kind not in ("ca", "today_t20", "token", "x_post", "new_ca", "NEW_CA") and not rec.get("ca") and not rec.get("address"):
        return None
    ch = norm_chain(rec.get("chain"))
    ts = str(rec.get("ts") or iso())
    src = str(rec.get("source") or rec.get("client_tag") or kind or "alert")
    eid = str(rec.get("id") or event_id(h, ca, src, ts))
    return {
        "id": eid,
        "handle": h,
        "name": rec.get("name"),
        "ca": ca,
        "address": ca,
        "chain": ch,
        "chain_note": chain_note(ch, ca),
        "wallet_note": chain_note(ch, ca),
        "ts": ts,
        "confidence": rec.get("confidence"),
        "ca_fixed": bool(rec.get("ca_fixed")),
        "ca_fixed_reason": rec.get("ca_fixed_reason"),
        "ca_status": rec.get("ca_status") or ("confirmed" if rec.get("ca_fixed") else None),
        "is_token": rec.get("is_token", True),
        "kind": kind or "ca",
        "source": src,
        "evidence_url": rec.get("tweet_url") or rec.get("evidence_url") or rec.get("site"),
    }


def collect_events(projects: list[dict]) -> list[dict]:
    handles = {norm_h(p["handle"]) for p in projects}
    by_id: dict[str, dict] = {}

    for path in ALERT_FILES:
        if not path.exists():
            continue
        try:
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                ev = from_alert_line(rec, handles)
                if ev:
                    by_id[ev["id"]] = ev
        except Exception as e:
            print(f"[today_ca_push] read {path.name}: {e}", flush=True)

    # locks
    if LOCKS.exists():
        try:
            doc = json.loads(LOCKS.read_text(encoding="utf-8"))
            marks = doc if isinstance(doc, list) else (doc.get("locks") or doc.get("items") or doc.get("marks") or [])
            if isinstance(marks, dict):
                marks = [{"handle": k, **v} if isinstance(v, dict) else {"handle": k} for k, v in marks.items()]
            for rec in marks:
                if not isinstance(rec, dict):
                    continue
                h = rec.get("handle") or ""
                if norm_h(h) not in handles:
                    continue
                ca = (rec.get("address") or rec.get("ca") or "").strip()
                if not ca:
                    continue
                ch = norm_chain(rec.get("chain"))
                ts = str(rec.get("locked_at") or rec.get("ts") or iso())
                eid = event_id(h, ca, "ca_lock", ts)
                by_id[eid] = {
                    "id": eid,
                    "handle": h,
                    "name": rec.get("name"),
                    "ca": ca,
                    "address": ca,
                    "chain": ch,
                    "chain_note": chain_note(ch, ca),
                    "wallet_note": chain_note(ch, ca),
                    "ts": ts,
                    "confidence": "confirmed",
                    "ca_fixed": True,
                    "ca_fixed_reason": rec.get("note") or "ca_lock",
                    "ca_status": "confirmed",
                    "is_token": True,
                    "kind": "ca",
                    "source": "ca_lock",
                    "evidence_url": rec.get("post_url"),
                }
        except Exception as e:
            print(f"[today_ca_push] locks: {e}", flush=True)

    # finds (optional)
    if FINDS.exists():
        try:
            doc = json.loads(FINDS.read_text(encoding="utf-8"))
            items = doc if isinstance(doc, list) else (doc.get("items") or doc.get("finds") or [])
            for rec in items:
                if not isinstance(rec, dict):
                    continue
                h = rec.get("handle") or ""
                if norm_h(h) not in handles:
                    continue
                ca = (rec.get("address") or rec.get("ca") or "").strip()
                if not ca:
                    continue
                ch = norm_chain(rec.get("chain"))
                ts = str(rec.get("ts") or rec.get("found_at") or iso())
                eid = event_id(h, ca, str(rec.get("source") or "ca_find"), ts)
                if eid in by_id:
                    continue
                by_id[eid] = {
                    "id": eid,
                    "handle": h,
                    "name": rec.get("name"),
                    "ca": ca,
                    "address": ca,
                    "chain": ch,
                    "chain_note": chain_note(ch, ca),
                    "wallet_note": chain_note(ch, ca),
                    "ts": ts,
                    "confidence": rec.get("confidence"),
                    "ca_fixed": bool(rec.get("ca_fixed")),
                    "ca_fixed_reason": rec.get("ca_fixed_reason"),
                    "ca_status": rec.get("ca_status"),
                    "is_token": rec.get("is_token", True),
                    "kind": "ca",
                    "source": rec.get("source") or "ca_find",
                    "evidence_url": rec.get("tweet_url") or rec.get("post_url"),
                }
        except Exception as e:
            print(f"[today_ca_push] finds: {e}", flush=True)

    events = list(by_id.values())
    try:  # 2026-10-29 Capta: drop denied CAs + CAs from personal/KOL handles
        from ca_confidence import denied_ca, non_project_account
        events = [e for e in events
                  if not denied_ca(e.get("ca")) and not non_project_account(e.get("handle"))[0]]
    except Exception as e:
        print(f"[today_ca_push] deny filter: {e}", flush=True)
    events.sort(key=lambda e: str(e.get("ts") or ""), reverse=True)
    return events[:500]


def push_event(event: dict, *, projects: list[dict] | None = None) -> dict:
    """Realtime single-event push (T-20 / deployer). Always includes chain_note."""
    try:  # 2026-10-29 Capta
        from ca_confidence import denied_ca, non_project_account
        if denied_ca(event.get("ca") or event.get("address")) or non_project_account(event.get("handle"))[0]:
            return {"ok": False, "skipped": "denied_or_kol"}
    except Exception:
        pass
    ch = norm_chain(event.get("chain"))
    ca = (event.get("ca") or event.get("address") or "").strip()
    body_event = {
        **event,
        "ca": ca,
        "address": ca,
        "chain": ch,
        "chain_note": event.get("chain_note") or chain_note(ch, ca),
        "wallet_note": event.get("wallet_note") or chain_note(ch, ca),
    }
    payload: dict[str, Any] = {
        "event": body_event,
        "client_id": event.get("client_id") or "box-today-ca",
        "replace_projects": False,
    }
    if projects is not None:
        payload["projects"] = projects
        payload["replace_projects"] = True
    return _post(payload)


def sync_all() -> dict:
    projects = load_today()
    events = collect_events(projects)
    # backfill project.chain from latest CA event when list says 未知/empty
    best_ch: dict[str, str] = {}
    for e in events:
        h = norm_h(e.get("handle"))
        ch = norm_chain(e.get("chain"))
        if h and ch and h not in best_ch:
            best_ch[h] = ch
    for p in projects:
        ch = norm_chain(p.get("chain"))
        if not ch or ch in ("未知", "unknown", "Unknown"):
            fill = best_ch.get(norm_h(p.get("handle")))
            if fill:
                p["chain"] = fill
                p["chain_note"] = f"链:{fill}"
        else:
            p["chain"] = ch
            p["chain_note"] = f"链:{ch}"
    return _post(
        {
            "projects": projects,
            "events": events,
            "client_id": "box-today-ca-sync",
            "replace_projects": True,
            "replace_events": True,
        }
    )


def _post(payload: dict) -> dict:
    tok = token()
    if not tok:
        return {"ok": False, "error": "no_token"}
    r = requests.post(
        f"{API}/v1/today/cas/push",
        json=payload,
        headers={"X-Pad-Hunter-Token": tok, "User-Agent": UA},
        timeout=20,
    )
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:300]}
    return {"ok": r.status_code < 300, "code": r.status_code, "body": body}


def main(argv: list[str]) -> int:
    cmd = (argv[1] if len(argv) > 1 else "sync").strip()
    if cmd in ("sync", "push", "all"):
        r = sync_all()
        print(json.dumps(r, ensure_ascii=False)[:2000])
        return 0 if r.get("ok") else 1
    if cmd == "dry":
        projects = load_today()
        events = collect_events(projects)
        print(json.dumps({"projects": len(projects), "events": len(events), "sample": events[:3], "projects_sample": projects[:2]}, ensure_ascii=False, indent=2)[:4000])
        return 0
    print("usage: today_ca_push.py [sync|dry]")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
