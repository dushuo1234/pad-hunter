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
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from push_date import ENTRY_FIELDS, apply_push_date, canonical_push_date, parse_entry_time

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


def follower_count(project: Dict[str, Any]) -> int:
    followers = project.get("followers")
    if isinstance(followers, bool):
        return 0
    if isinstance(followers, (int, float)) and int(followers) > 0:
        return int(followers)
    if isinstance(followers, str):
        stripped = followers.strip()
        if stripped.isdigit():
            return int(stripped)
        parsed = parse_fans(stripped)
        if parsed:
            return parsed
    return parse_fans(str(project.get("fans") or ""))


def normalize_source(value: str) -> str:
    text = value.strip()
    if not text:
        return ""
    if text.startswith("telegram:") or ":" in text:
        return text
    return f"telegram:{text}"


def to_candidate(project: Dict[str, Any], rank: int, default_source: str = "telegram:项目推送") -> Dict[str, Any]:
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

    source = normalize_source(str(project.get("source") or "")) or default_source
    row: Dict[str, Any] = {
        "rank": rank,
        "handle": handle,
        "name": str(project.get("name") or handle or "未命名"),
        "followers": follower_count(project),
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
        "source": source,
    }
    for key in ENTRY_FIELDS:
        if key == "date_iso":
            continue
        value = project.get(key)
        if value in (None, ""):
            camel = key.split("_")[0] + "".join(part.capitalize() for part in key.split("_")[1:])
            value = project.get(camel)
        if value not in (None, ""):
            row[key] = value
    apply_push_date(row, project)
    for key in (
        "ca",
        "ca_chain",
        "ca_source",
        "listing_signal",
        "listing_at",
        "launch_at",
        "listing_at_source",
        "last_checked",
        "onchain_notes",
    ):
        value = project.get(key)
        if value not in (None, ""):
            row[key] = value
    sites = project.get("sites")
    if isinstance(sites, list) and sites:
        urls = []
        for site in sites:
            if isinstance(site, str) and site.strip():
                urls.append(site.strip())
            elif isinstance(site, dict) and site.get("url"):
                urls.append(str(site["url"]))
        if urls:
            row["sites"] = urls
    return row


def load_projects(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [p for p in data if isinstance(p, dict)]
    if isinstance(data, dict):
        candidates = data.get("candidates")
        if isinstance(candidates, list):
            return [p for p in candidates if isinstance(p, dict)]
    raise ValueError(f"unrecognized snapshot shape: {path}")


def channel_name(source: str) -> str:
    return source.split(":", 1)[-1] if ":" in source else source


def goal_for(sources: List[str]) -> str:
    names = [channel_name(source) for source in sources if source]
    if len(names) == 2:
        inner = f"「{names[0]}」与「{names[1]}」"
    elif len(names) > 2:
        inner = "、".join(f"「{name}」" for name in names)
    else:
        inner = f"「{names[0] if names else '项目推送'}」"
    return f"Telegram{inner}· 按链与类型分类"


def preferred_sources(found: List[str]) -> List[str]:
    order = ["telegram:项目推送监控", "telegram:项目推送"]

    def key(source: str) -> tuple:
        return (order.index(source) if source in order else len(order), source)

    return sorted(dict.fromkeys(found), key=key)


def resolve_source(projects: List[Dict[str, Any]], explicit: str) -> str:
    if explicit.strip():
        return normalize_source(explicit)
    env = os.environ.get("TG_SOURCE", "").strip()
    if env:
        return normalize_source(env)
    found = [normalize_source(str(p.get("source") or "")) for p in projects]
    found = [item for item in found if item]
    unique = list(dict.fromkeys(found))
    if len(unique) == 1:
        return unique[0]
    return "telegram:项目推送"


def previous_by_handle(out: Path) -> Dict[str, Dict[str, Any]]:
    """Earlier site rows, used only to keep the first push date. Missing file is fine."""
    if not out.exists():
        return {}
    try:
        old = json.loads(out.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = old.get("candidates") if isinstance(old, dict) else None
    if not isinstance(rows, list):
        return {}
    found: Dict[str, Dict[str, Any]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        handle = str(item.get("handle") or "").lstrip("@").lower()
        if not handle:
            continue
        current = found.get(handle)
        if current is None:
            found[handle] = item
            continue
        found[handle] = _earlier_entry(current, item)
    return found


def _entry_ms(record: Dict[str, Any]) -> Optional[int]:
    text = canonical_push_date(record)
    parsed = parse_entry_time(text)
    return parsed[0] if parsed else None


def _earlier_entry(left: Dict[str, Any], right: Dict[str, Any]) -> Dict[str, Any]:
    left_ms = _entry_ms(left)
    right_ms = _entry_ms(right)
    if right_ms is not None and (left_ms is None or right_ms < left_ms):
        return right
    return left


def write_site(projects: List[Dict[str, Any]], out: Path, source: str, merge: bool) -> None:
    earlier = previous_by_handle(out)
    ordered = sorted(projects, key=lambda p: as_int(p.get("message_id")), reverse=True)
    candidates = [to_candidate(p, i, source) for i, p in enumerate(ordered, start=1)]
    if merge and out.exists():
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"warning: could not merge existing {out}: {exc}")
            old = None
        old_list = old.get("candidates") if isinstance(old, dict) else None
        if isinstance(old_list, list):
            kept = []
            for item in old_list:
                if not isinstance(item, dict):
                    continue
                item_source = normalize_source(str(item.get("source") or ""))
                if not item_source and isinstance(old, dict):
                    item_source = normalize_source(str(old.get("source") or ""))
                if item_source and item_source != source:
                    kept.append(item)
            candidates = kept + candidates
            candidates.sort(
                key=lambda p: (str(p.get("date_iso") or ""), as_int(p.get("message_id"))),
                reverse=True,
            )
    for index, candidate in enumerate(candidates, start=1):
        candidate["rank"] = index
        handle = str(candidate.get("handle") or "").lstrip("@").lower()
        apply_push_date(candidate, earlier.get(handle))
    sources = preferred_sources(
        [str(item.get("source") or source) for item in candidates if isinstance(item, dict)]
    )
    payload_source = sources[0] if sources else source
    # Stable rank: newest message first when not merging. Merge re-ranks by date.
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "goal": goal_for(sources or [source]),
        "source": payload_source,
        "sources": sources or [source],
        "candidates": candidates,
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
    ap.add_argument(
        "--source",
        default="",
        help="channel id stamped on candidates (default TG_SOURCE or telegram:项目推送)",
    )
    ap.add_argument(
        "--merge",
        action="store_true",
        help="keep candidates from other sources already in the output file",
    )
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
    source = resolve_source(projects, args.source)
    print(f"source: {source} merge={bool(args.merge)}")
    write_site(projects, out, source, bool(args.merge))

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
