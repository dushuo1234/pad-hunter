#!/usr/bin/env python3
"""Fetch latest 「项目推送」 cards and write Pad Hunter candidates.json.

The Vite app reads public/data/candidates.json. This script converts the
Telegram snapshot (chain, category, status, listing, risk, …) into that schema.
It never prints credentials. Telethon sessions and the local .data directory
stay untracked.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[1]
DATA_DIR = Path(os.environ.get("TG_DATA_DIR", SCRIPT_DIR / ".data")).expanduser()
SNAPSHOT = DATA_DIR / "projects.json"
FETCH = SCRIPT_DIR / "fetch_and_classify.py"
DEFAULT_OUT = REPO_ROOT / "public" / "data" / "candidates.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")

FANS_RE = re.compile(r"([\d]+(?:[.,]\d+)?)\s*([kKmM万])?")


def python_bin() -> str:
    return sys.executable


def parse_fans(fans: str) -> int:
    if not fans:
        return 0
    match = FANS_RE.search(fans.replace(",", ""))
    if not match:
        return 0
    try:
        value = float(match.group(1))
    except ValueError:
        return 0
    unit = match.group(2) or ""
    if unit.lower() == "k":
        value *= 1_000
    elif unit.lower() == "m":
        value *= 1_000_000
    elif unit == "万":
        value *= 10_000
    return int(value)


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def to_candidate(project: Dict[str, Any], rank: int) -> Dict[str, Any]:
    """Map a Telegram card, or an already-shaped site record, into candidates.json."""
    handle = str(project.get("handle") or project.get("twitter_handle") or "").lstrip("@")
    message_id = project.get("message_id")
    date_iso = project.get("date_iso") or ""
    x_url = str(project.get("tweet_url") or project.get("x_url") or "")
    if not x_url and handle:
        x_url = f"https://x.com/{handle}"

    why = str(project.get("why") or project.get("summary_cn") or project.get("summary_en") or "")
    bio = str(project.get("bio") or project.get("summary_en") or "")
    notes = project.get("notes")
    if not notes and message_id:
        notes = f"msg {message_id} · {date_iso}".strip()

    score = project.get("score")
    if not isinstance(score, (int, float)):
        score = 50

    followers = project.get("followers")
    if not isinstance(followers, (int, float)) or int(followers) == 0:
        followers = parse_fans(str(project.get("fans") or ""))

    return {
        "rank": rank,
        "handle": handle,
        "name": str(project.get("name") or handle or "未命名"),
        "followers": as_int(followers),
        "kol_followers": as_int(project.get("kol_followers")),
        "bio": bio,
        "why": why,
        "score": score,
        "tweet_url": x_url,
        "chain": str(project.get("chain") or "未知"),
        "category": str(project.get("category") or "其他"),
        "status": str(project.get("status") or ""),
        "listing": str(project.get("listing") or ""),
        "risk": str(project.get("risk") or ""),
        "notes": notes or "",
        "message_id": message_id,
        "date_iso": date_iso,
    }


def load_projects(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        candidates = data.get("candidates")
        if isinstance(candidates, list):
            return [p for p in candidates if isinstance(p, dict)]
    raise ValueError(f"unrecognized snapshot shape: {path}")


def write_site(projects: List[Dict[str, Any]], out: Path) -> None:
    ordered = sorted(projects, key=lambda p: as_int(p.get("message_id")), reverse=True)
    # Stable rank: newest message first. If message ids tie, keep prior order.
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "goal": "Telegram「项目推送」· 按链与类型分类",
        "source": "telegram:项目推送",
        "candidates": [to_candidate(p, i) for i, p in enumerate(ordered, start=1)],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(out, 0o644)


def run_fetch(limit: int, offline: bool) -> int:
    cmd = [python_bin(), str(FETCH), str(limit)]
    if offline:
        cmd.append("--offline")
    print(f"fetch: {'offline' if offline else 'live'} limit={limit}")
    proc = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONUNBUFFERED": "1", "TG_DATA_DIR": str(DATA_DIR)},
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    for line in out.splitlines():
        low = line.lower()
        if any(k in low for k in ("api_hash", "password", "phone=", "proxy pass", "proxy_pass")):
            continue
        print(line)
    return proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync Telegram 项目推送 into Pad Hunter candidates.json")
    ap.add_argument("--limit", type=int, default=100, help="messages to fetch (default 100)")
    ap.add_argument("--offline", action="store_true", help="skip Telegram; classify the local sample")
    ap.add_argument("--no-fetch", action="store_true", help="only convert the existing snapshot")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="candidates.json path")
    ap.add_argument("--allow-empty", action="store_true", help="allow writing an empty candidate list")
    args = ap.parse_args()

    now = datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
    print(f"sync_start: {now} Asia/Shanghai")

    if not args.no_fetch:
        if not FETCH.exists():
            print(f"error: missing fetch script {FETCH}", file=sys.stderr)
            return 1
        code = run_fetch(args.limit, args.offline)
        if code != 0:
            print(f"warning: fetch exited {code}; will still try to convert the snapshot")
    else:
        print("fetch: skipped (--no-fetch)")

    if not SNAPSHOT.exists():
        print(f"error: missing snapshot {SNAPSHOT}", file=sys.stderr)
        return 1

    try:
        projects = load_projects(SNAPSHOT)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not projects and not args.allow_empty:
        print("error: refusing to overwrite site data with 0 projects", file=sys.stderr)
        return 1

    out = Path(args.out)
    write_site(projects, out)

    written = json.loads(out.read_text(encoding="utf-8"))
    candidates = written["candidates"]
    from collections import Counter

    chains = Counter((p.get("chain") or "未知") for p in candidates)
    cats = Counter((p.get("category") or "未知") for p in candidates)
    print(f"site_projects: {len(candidates)}")
    print("chains: " + ", ".join(f"{k}={v}" for k, v in chains.most_common()))
    print("categories: " + ", ".join(f"{k}={v}" for k, v in cats.most_common()))
    print(f"snapshot: {SNAPSHOT}")
    print(f"site_data: {out}")
    print("sync_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
