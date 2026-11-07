#!/usr/bin/env python3
"""Fetch latest project cards and sync PushRadar site data snapshot."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/home/box/.tg-monitor")
SITE = Path("/workspace/push-radar")
SITE_DATA = SITE / "data" / "projects.json"
SNAPSHOT = BASE / "projects.json"
JSONL = BASE / "projects.jsonl"
FETCH = BASE / "fetch_and_classify.py"
VENV_PY = BASE / "venv" / "bin" / "python"
SHANGHAI = ZoneInfo("Asia/Shanghai")
REMOVED_LAUNCHED = Path("/workspace/project-monitor/removed_launched.json")


def python_bin() -> str:
    if VENV_PY.exists():
        return str(VENV_PY)
    return sys.executable


def copy_snapshot() -> int:
    SITE_DATA.parent.mkdir(parents=True, exist_ok=True)
    if not SNAPSHOT.exists():
        raise FileNotFoundError(f"missing snapshot: {SNAPSHOT}")
    # Prefer copy so site stays readable even if source is 0600
    shutil.copy2(SNAPSHOT, SITE_DATA)
    os.chmod(SITE_DATA, 0o644)
    data = json.loads(SITE_DATA.read_text(encoding="utf-8"))
    # Blocklist: launched projects soft-deleted by prune_launched.py must not come back
    try:
        rem = json.loads(REMOVED_LAUNCHED.read_text(encoding="utf-8"))
        items = rem.get("items", []) if isinstance(rem, dict) else rem
        blocked = {(e.get("handle") or "").lstrip("@").lower() for e in items if not e.get("restored")}
        if blocked and isinstance(data, list):
            data = [p for p in data
                    if (p.get("twitter_handle") or p.get("handle") or "").lstrip("@").lower() not in blocked]
            SITE_DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"blocklist: filtered launched handles={len(blocked)}")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"warning: blocklist filter failed: {e}")
    return len(data) if isinstance(data, list) else 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync Telegram projects into PushRadar site")
    ap.add_argument("--limit", type=int, default=100, help="messages to fetch (default 100)")
    ap.add_argument("--offline", action="store_true", help="skip Telegram; only copy existing snapshot")
    ap.add_argument("--no-fetch", action="store_true", help="alias of --offline")
    args = ap.parse_args()

    offline = args.offline or args.no_fetch
    now = datetime.now(SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")
    print(f"sync_start: {now} Asia/Shanghai")
    print(f"site: {SITE}")

    if not offline:
        if not FETCH.exists():
            print(f"error: missing fetch script {FETCH}", file=sys.stderr)
            return 1
        cmd = [
            python_bin(),
            str(FETCH),
            str(args.limit),
            "--board-md",
            "/tmp/push-radar-board.md",
            "--board-html",
            "/tmp/push-radar-board.html",
        ]
        print(f"fetch: limit={args.limit}")
        # Do not print env or credentials
        proc = subprocess.run(
            cmd,
            cwd=str(BASE),
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        # Filter credential-looking lines just in case
        out = (proc.stdout or "") + (proc.stderr or "")
        for line in out.splitlines():
            low = line.lower()
            if any(k in low for k in ("api_hash", "password", "phone=", "proxy pass")):
                continue
            print(line)
        if proc.returncode != 0:
            print(f"warning: fetch exited {proc.returncode}; will still try to copy snapshot")
    else:
        print("fetch: skipped (--offline)")

    try:
        n = copy_snapshot()
    except Exception as e:
        print(f"error: copy failed: {e}", file=sys.stderr)
        return 1

    # light stats
    try:
        projects = json.loads(SITE_DATA.read_text(encoding="utf-8"))
        from collections import Counter

        chains = Counter((p.get("chain") or "未知") for p in projects)
        cats = Counter((p.get("category") or "未知") for p in projects)
        print(f"site_projects: {n}")
        print("chains: " + ", ".join(f"{k}={v}" for k, v in chains.most_common()))
        print("categories: " + ", ".join(f"{k}={v}" for k, v in cats.most_common()))
        print(f"jsonl: {JSONL}")
        print(f"snapshot: {SNAPSHOT}")
        print(f"site_data: {SITE_DATA}")
    except Exception as e:
        print(f"warning: stats failed: {e}")
        print(f"site_projects: {n}")

    print("sync_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
