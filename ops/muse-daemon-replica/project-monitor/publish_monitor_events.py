#!/usr/bin/env python3
"""Rebuild monitor_events.json for GitHub Pages from local scan artifacts.

Outputs:
  /workspace/publish-pages-data/monitor_events.json
  /cursor/stores/.../publish-pages-data/monitor_events.json
  /workspace/push-radar/data/monitor_events.json (mirror)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE = Path("/workspace/project-monitor")
PUBLISH = Path("/workspace/publish-pages-data")
STORE = Path("/cursor/stores/store-b953e26e-8884-4159-b9a8-d2e6295761c8/publish-pages-data")
MIRROR = Path("/workspace/push-radar/data")
BUILDER = BASE / "build_monitor_events.py"
TZ = timezone(timedelta(hours=8))


def load(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    tmp = BASE / "monitor_events.base.json"
    cmd = [
        sys.executable,
        str(BUILDER),
        "--latest",
        str(BASE / "latest.json"),
        "--listing-scan",
        str(BASE / "listing_scan_latest.json"),
        "--watchlist",
        str(BASE / "watchlist.json"),
        "--out",
        str(tmp),
    ]
    # Builder exits if a file is missing; only pass existing ones
    # Re-check existence
    if not (BASE / "latest.json").exists():
        cmd = [c for c in cmd if c != "--latest" and c != str(BASE / "latest.json")]
    if not (BASE / "listing_scan_latest.json").exists():
        cmd = [c for c in cmd if c != "--listing-scan" and c != str(BASE / "listing_scan_latest.json")]
    if not (BASE / "watchlist.json").exists():
        cmd = [c for c in cmd if c != "--watchlist" and c != str(BASE / "watchlist.json")]
    if "--out" not in cmd:
        print("no inputs", file=sys.stderr)
        return 1
    # rebuild builder args cleanly
    cmd = [sys.executable, str(BUILDER), "--out", str(tmp)]
    if (BASE / "latest.json").exists():
        cmd += ["--latest", str(BASE / "latest.json")]
    if (BASE / "listing_scan_latest.json").exists():
        cmd += ["--listing-scan", str(BASE / "listing_scan_latest.json")]
    if (BASE / "watchlist.json").exists():
        cmd += ["--watchlist", str(BASE / "watchlist.json")]
    subprocess.check_call(cmd)

    doc = load(tmp) or {"events": []}
    events = [e for e in (doc.get("events") or []) if not e.get("sample")]
    seen = set()
    for e in events:
        kind = e.get("kind")
        h = (e.get("handle") or "").lower()
        if kind == "ca":
            seen.add(("ca", h, (e.get("ca") or "").lower()))
        elif kind == "listing_signal":
            sig = ((e.get("listing_signal") or {}).get("signal") or "")
            seen.add(("sig", h, sig))

    now = datetime.now(TZ)
    # ca_finds
    ca = load(BASE / "ca_finds.json") or {}
    for f in ca.get("finds") or []:
        if not isinstance(f, dict):
            continue
        handle = str(f.get("handle") or "").lstrip("@")
        addr = str(f.get("address") or f.get("ca") or "").strip()
        if not handle or not addr:
            continue
        key = ("ca", handle.lower(), addr.lower())
        if key in seen:
            continue
        seen.add(key)
        at = str(f.get("detected_at") or f.get("at") or now.isoformat())
        events.append(
            {
                "id": f"ca|{handle.lower()}|{at}|{addr}",
                "kind": "ca",
                "at": at,
                "handle": handle,
                "name": str(f.get("project") or f.get("name") or handle),
                "ca": addr,
                "ca_chain": f.get("chain") or None,
                "ca_source": f.get("source") or "ca_finds",
                "note": f.get("note") or "",
            }
        )

    # listing_times (prefer publish-pages / live-shaped times[])
    lt = load(PUBLISH / "listing_times.json") or load(BASE / "listing_times.json") or {}
    times = []
    if isinstance(lt, dict):
        # Pages sometimes exposes sticky `times`; full extract uses `items`
        for key in ("times", "items"):
            chunk = lt.get(key)
            if isinstance(chunk, list):
                times.extend(chunk)
    elif isinstance(lt, list):
        times = lt
    for t in times:
        if not isinstance(t, dict):
            continue
        handle = str(t.get("handle") or "").lstrip("@")
        at = str(t.get("listing_at") or "").strip()
        if not handle or not at:
            continue
        signal = f"开盘时间 {at}"
        key = ("sig", handle.lower(), signal)
        if key in seen:
            continue
        seen.add(key)
        name = str(t.get("name") or handle)
        events.append(
            {
                "id": f"listing_signal|{handle.lower()}|listing_at|{at}",
                "kind": "listing_signal",
                "at": at,
                "handle": handle,
                "name": name,
                "listing_signal": {
                    "name": name,
                    "handle": handle,
                    "signal": signal,
                    "prev": None,
                    "source": str(t.get("listing_at_source") or "listing_times"),
                },
            }
        )

    events.sort(key=lambda e: e.get("at") or "", reverse=True)
    payload = {
        "generated_at": now.isoformat(),
        "note": "监控事件按 handle 归到项目时间线。由 latest + listing_scan + watchlist + ca_finds + listing_times 汇总。sample 已剔除。",
        "events": events,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for dest in (PUBLISH, STORE, MIRROR):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "monitor_events.json").write_text(text, encoding="utf-8")
    print(f"monitor_events.json: {len(events)} events -> {PUBLISH / 'monitor_events.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
