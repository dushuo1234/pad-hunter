#!/usr/bin/env python3
"""Publish local ca_finds.json to pad-hunter GitHub Pages (main public/data/).

Also mirrors into publish-pages-data + push-radar/data + bot store when present.
Soft-fails if GitHub auth is missing (does not raise).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from publish_pages_file import put_file, put_file_to_branch

BASE = Path("/workspace/project-monitor")
LOCAL = BASE / "ca_finds.json"
REMOTE = "public/data/ca_finds.json"
MIRRORS = [
    Path("/workspace/push-radar/data/ca_finds.json"),
    Path("/workspace/publish-pages-data/ca_finds.json"),
]


def mirror_local() -> None:
    if not LOCAL.is_file():
        return
    for dest in MIRRORS:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LOCAL, dest)
        except OSError as e:
            print(f"[publish_ca_finds] mirror warn {dest}: {e}", flush=True)


def publish(*, force: bool = False) -> int:
    mirror_local()
    if not LOCAL.is_file():
        print("[publish_ca_finds] missing ca_finds.json", flush=True)
        return 2
    try:
        doc = json.loads(LOCAL.read_text(encoding="utf-8"))
        n = doc.get("count") if isinstance(doc, dict) else None
    except Exception:
        n = None
    msg = f"data: ca_finds auto ({n} finds)" if n is not None else "data: ca_finds auto"
    rc = put_file(LOCAL, REMOTE, message=msg, force=force)
    # Also write live Pages branch (vite force_orphan can lag / cancel-in-progress races)
    rc2 = put_file_to_branch(LOCAL, "data/ca_finds.json", "gh-pages", message=msg + " (gh-pages)", force=force)
    return rc if rc else rc2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--watch", action="store_true", help="Poll mtime every few seconds and publish on change")
    ap.add_argument("--interval", type=float, default=3.0)
    args = ap.parse_args()
    if args.watch:
        import time

        last = None
        print(f"[publish_ca_finds] watcher interval={args.interval}s", flush=True)
        while True:
            try:
                mtime = LOCAL.stat().st_mtime if LOCAL.is_file() else None
                if mtime is not None and mtime != last:
                    last = mtime
                    publish(force=False)
            except Exception as e:
                print(f"[publish_ca_finds] watch error: {e}", flush=True)
            time.sleep(max(1.0, args.interval))
    try:
        return publish(force=args.force)
    except Exception as e:
        print(f"[publish_ca_finds] error: {e}", flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
