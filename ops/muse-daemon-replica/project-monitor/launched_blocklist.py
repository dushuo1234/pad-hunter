#!/usr/bin/env python3
"""Shared launched-handle blocklist + workbench prune.

removed_launched.json (restored=false) is the source of truth. Every prune /
mark / workbench sync must drop those handles from workbench_active.json so the
realtime poller and the browser workbench stop tracking 已开盘 projects.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
REMOVED = BASE / "removed_launched.json"
WORKBENCH = BASE / "workbench_active.json"
LAUNCHED_DATA = Path("/workspace/push-radar/data/launched.json")
TZ = ZoneInfo("Asia/Shanghai")


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def hkey(h: str | None) -> str:
    return (h or "").lstrip("@").strip().lower()


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def dump_json(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_blocklist() -> set[str]:
    """Handles soft-deleted as 已开盘 (restored=false), plus launched.json."""
    blocked: set[str] = set()
    rem = load_json(REMOVED, {})
    items = rem.get("items") if isinstance(rem, dict) else rem
    for e in items or []:
        if isinstance(e, dict) and not e.get("restored"):
            k = hkey(e.get("handle"))
            if k:
                blocked.add(k)
    launched = load_json(LAUNCHED_DATA, {})
    for e in (launched.get("items") if isinstance(launched, dict) else launched) or []:
        if isinstance(e, dict):
            k = hkey(e.get("handle"))
            if k:
                blocked.add(k)
    return blocked


def prune_workbench(block: set[str] | None = None) -> dict:
    """Drop blocklisted handles from workbench_active.json. Idempotent.

    Returns {before, after, dropped:[{handle,name}], updated_at}.
    """
    block = set(block) if block is not None else load_blocklist()
    wb = load_json(WORKBENCH, {"items": []}) or {"items": []}
    items = list(wb.get("items") or [])
    before = len(items)
    kept, dropped = [], []
    for it in items:
        if not isinstance(it, dict):
            continue
        k = hkey(it.get("handle"))
        if k and k in block:
            dropped.append({"handle": it.get("handle"), "name": it.get("name")})
            continue
        kept.append(it)
    ts = now_iso()
    if dropped:
        wb["items"] = kept
        wb["count"] = len(kept)
        wb["last_prune_at"] = ts
        wb["last_pruned_handles"] = [d.get("handle") for d in dropped]
        note = wb.get("note") or ""
        if "blocklist" not in note.lower():
            wb["note"] = (
                (note + " " if note else "")
                + "Launched handles (removed_launched blocklist) are stripped on every prune/sync."
            ).strip()
        dump_json(WORKBENCH, wb)
    return {
        "before": before,
        "after": len(kept),
        "dropped": dropped,
        "updated_at": ts,
    }


def filter_handles(handles: list[str], block: set[str] | None = None) -> tuple[list[str], list[str]]:
    """Split handles into (kept, dropped) against the blocklist."""
    block = set(block) if block is not None else load_blocklist()
    kept, dropped = [], []
    for h in handles:
        k = hkey(h)
        if k and k in block:
            dropped.append(h)
        else:
            kept.append(h)
    return kept, dropped
