#!/usr/bin/env python3
"""Layer-1 sniper watcher: poll ca_finds for HIGH-CONF / confirmed → fire_buy (dry_run).

  python3 sniper_watcher.py once          # single pass
  python3 sniper_watcher.py watch         # poll loop (~0.5s on mtime)
  python3 sniper_watcher.py inject-find   # wrap sniper_buy inject

6551 WSS last-layer: not started here yet (see sniper_6551.py stub next).
Does NOT call real baw while sniper_config dry_run=true.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from sniper_buy import fire_from_find, fire_buy, is_high_conf_find, load_config  # noqa: E402

CA_FINDS = BASE / "ca_finds.json"
WB = BASE / "workbench_active.json"
STATE = BASE / "alerts" / "sniper_watcher_state.json"
POLL = float(os.environ.get("SNIPER_POLL_S", "0.5"))


def _load_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _wb_handles() -> set[str]:
    d = _load_json(WB) or {}
    items = d.get("items") if isinstance(d, dict) else d
    out = set()
    if isinstance(items, list):
        for it in items:
            h = (it.get("handle") or "").strip().lstrip("@").lower()
            if h:
                out.add(h)
    return out


def _seen_load() -> set[str]:
    d = _load_json(STATE) or {}
    return set(d.get("seen_find_keys") or [])


def _seen_save(keys: set[str]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    # keep last 5k
    clipped = sorted(keys)[-5000:]
    tmp.write_text(json.dumps({"seen_find_keys": clipped, "count": len(clipped)}, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(STATE)


def _find_key(f: dict) -> str:
    h = (f.get("handle") or "").strip().lstrip("@").lower()
    a = (f.get("address") or "").strip()
    a = a.lower() if a.lower().startswith("0x") else a
    return f"{h}|{a}|{f.get('ca_status')}|{f.get('detected_at')}"


def scan_once(*, only_workbench: bool = False) -> list[dict]:
    cfg = load_config()
    data = _load_json(CA_FINDS) or {}
    finds = data.get("finds") if isinstance(data, dict) else data
    if not isinstance(finds, list):
        return []
    wb = _wb_handles() if only_workbench else None
    seen = _seen_load()
    out = []
    dirty = False
    for f in finds:
        if not is_high_conf_find(f):
            continue
        if wb is not None:
            h = (f.get("handle") or "").strip().lstrip("@").lower()
            if h not in wb:
                continue
        k = _find_key(f)
        if k in seen:
            continue
        seen.add(k)
        dirty = True
        r = fire_from_find(f, source="high_conf")
        out.append(r)
    if dirty:
        _seen_save(seen)
    return out


def watch_loop(*, only_workbench: bool = False) -> None:
    print(f"[sniper_watcher] dry_run={load_config().get('dry_run')} poll={POLL}s ca_finds={CA_FINDS}", flush=True)
    last_mtime = 0.0
    while True:
        try:
            mt = CA_FINDS.stat().st_mtime if CA_FINDS.exists() else 0.0
            if mt != last_mtime:
                last_mtime = mt
                rows = scan_once(only_workbench=only_workbench)
                for r in rows:
                    print(json.dumps({k: r.get(k) for k in ("ts", "action", "project", "handle", "ca", "chain", "ms", "skipped_reason")}, ensure_ascii=False), flush=True)
        except Exception as e:
            print(f"[sniper_watcher] err {e}", flush=True)
        time.sleep(POLL)


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    once = sub.add_parser("once")
    once.add_argument("--workbench-only", action="store_true")
    w = sub.add_parser("watch")
    w.add_argument("--workbench-only", action="store_true")
    args = p.parse_args(argv)
    if args.cmd == "once":
        rows = scan_once(only_workbench=args.workbench_only)
        print(json.dumps({"fired": len(rows), "rows": [{k: r.get(k) for k in ('action','project','handle','ca','ms','skipped_reason')} for r in rows]}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "watch":
        watch_loop(only_workbench=args.workbench_only)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
