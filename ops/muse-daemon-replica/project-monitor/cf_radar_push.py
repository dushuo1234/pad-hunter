#!/usr/bin/env python3
"""Push candidate cards to Cloudflare Worker radar (api.adualpha.win).

Never prints the token. Network errors → WARN, exit 0.
Usage:
  cf_radar_push.py                  # seed newest 50 (upsert)
  cf_radar_push.py --handles a,b    # push those handles from candidates.json
  cf_radar_push.py --seed N
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
CANDIDATES = Path("/workspace/push-radar/data/candidates.json")
URL_FILE = BASE / "workbench_api_public_url_cf.txt"
TOKEN_FILE = BASE / "workbench_api_token.txt"
SH = ZoneInfo("Asia/Shanghai")
LOG = "[cf_radar_push]"


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def base_url() -> str:
    try:
        u = URL_FILE.read_text().strip().splitlines()[0].strip()
        if u.startswith("http"):
            return u.rstrip("/")
    except Exception:
        pass
    return "https://api.adualpha.win"


def load_candidates() -> list[dict]:
    try:
        doc = json.loads(CANDIDATES.read_text(encoding="utf-8"))
        return [c for c in (doc.get("candidates") or []) if isinstance(c, dict) and c.get("handle")]
    except Exception:
        return []


def pick(cards: list[dict], handles: list[str] | None, seed: int | None) -> list[dict]:
    if handles:
        want = {h.lstrip("@").strip().lower() for h in handles if h.strip()}
        out = []
        by = {str(c.get("handle") or "").lstrip("@").strip().lower(): c for c in cards}
        for h in want:
            if h in by:
                out.append(by[h])
        return out
    # newest first: prefer push_date / date_iso / completion_updated_at
    def key(c: dict) -> str:
        return str(c.get("push_date") or c.get("date_iso") or c.get("completion_updated_at") or "")
    sorted_cards = sorted(cards, key=key, reverse=True)
    n = seed if seed is not None else 50
    return sorted_cards[: max(0, n)]


def slim(card: dict) -> dict:
    """Keep frontend-useful fields; drop huge blobs."""
    keep = (
        "name", "handle", "chain", "category", "status", "listing", "listing_at",
        "listing_at_display", "already_listed", "within_next_3_days", "risk",
        "site", "tweet_url", "followers", "kol_followers", "bio", "why", "notes",
        "rank", "score", "source", "message_id", "date_iso", "push_date",
        "listing_signal", "js_completion", "js_completion_label",
        "contract_code_completion", "contract_code_completion_label",
        "game_code_completion", "game_code_completion_label", "high_completion",
        "completion_reasons", "completion_updated_at", "x_url", "sites",
    )
    out = {k: card[k] for k in keep if k in card}
    out["handle"] = str(card.get("handle") or "").strip()
    out["_pushed_at"] = now_iso()
    return out


def push(cards: list[dict], *, client_id: str = "tg_push_fast", mode: str = "upsert") -> dict:
    if not cards:
        return {"ok": True, "upserted": 0, "skipped": True}
    tok = TOKEN_FILE.read_text().strip()
    body = {
        "client_id": client_id,
        "cards": [slim(c) for c in cards],
        "mode": mode,
        "snapshot_meta": {"source": "box", "at": now_iso(), "n": len(cards)},
    }
    data = json.dumps(body, ensure_ascii=False).encode()
    req = urllib.request.Request(
        base_url() + "/v1/radar/push",
        data=data,
        method="POST",
        headers={
            "X-Pad-Hunter-Token": tok,
            "Content-Type": "application/json",
            "User-Agent": "pad-hunter-box/cf_radar_push",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())


def run(*, handles: list[str] | None = None, seed: int | None = None, client_id: str = "tg_push_fast") -> dict:
    try:
        cards = pick(load_candidates(), handles, seed if handles is None else None)
        res = push(cards, client_id=client_id, mode="upsert")
        res["pushed_handles"] = [c.get("handle") for c in cards]
        res["ok"] = True
        return res
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handles", default="", help="comma-separated handles to push")
    ap.add_argument("--seed", type=int, default=None, help="push newest N candidates")
    ap.add_argument("--client-id", default="tg_push_fast")
    args = ap.parse_args()
    handles = [h.strip() for h in args.handles.split(",") if h.strip()] or None
    seed = args.seed if args.seed is not None else (50 if not handles else None)
    res = run(handles=handles, seed=seed, client_id=args.client_id)
    if res.get("ok"):
        print(f"{LOG} ok upserted={res.get('upserted')} count={res.get('count')} handles={res.get('pushed_handles')}", flush=True)
    else:
        print(f"{LOG} WARN {res.get('error')}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
