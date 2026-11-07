#!/usr/bin/env python3
"""Merge JS-scan completion heuristics into candidates.json for 「即将开盘」.

Reads js_factory_scan_latest.json per-project completion fields and writes:
  js_completion, contract_code_completion, game_code_completion (+ labels)
onto matching candidates / watchlist rows. Does not invent listing times.
Never fails the routine hard — exit 0 even on soft errors.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
JS_LATEST = BASE / "js_factory_scan_latest.json"
WATCHLIST = BASE / "watchlist.json"
CANDIDATES = Path("/workspace/push-radar/data/candidates.json")
OUT = BASE / "site_completion.json"
MIRRORS = [
    Path("/workspace/publish-pages-data/candidates.json"),
    Path("/cursor/stores/store-b953e26e-8884-4159-b9a8-d2e6295761c8/publish-pages-data/candidates.json"),
]
SH = ZoneInfo("Asia/Shanghai")

COMP_KEYS = (
    "js_completion", "js_completion_label",
    "contract_code_completion", "contract_code_completion_label",
    "game_code_completion", "game_code_completion_label",
    "high_completion",
)


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def hkey(h: str | None) -> str:
    return (h or "").lower().lstrip("@").strip()


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def by_handle_from_js(doc: dict) -> dict[str, dict]:
    out = {}
    for r in doc.get("results") or []:
        h = hkey(r.get("handle"))
        if not h:
            continue
        row = {k: r.get(k) for k in COMP_KEYS if r.get(k) is not None}
        if r.get("completion"):
            for k in COMP_KEYS:
                if k not in row and r["completion"].get(k) is not None:
                    row[k] = r["completion"][k]
        if r.get("completion_reasons") or (r.get("completion") or {}).get("completion_reasons"):
            row["completion_reasons"] = (
                r.get("completion_reasons")
                or (r.get("completion") or {}).get("completion_reasons")
            )
        row["address_count"] = len(r.get("addresses") or [])
        row["factoryish_hits"] = r.get("factoryish_hits") or []
        row["config_sidecars"] = [c.get("path") for c in (r.get("config_sidecars") or [])]
        row["name"] = r.get("name")
        if row:
            out[h] = row
    return out


def apply_fields(target: dict, src: dict) -> bool:
    changed = False
    for k in COMP_KEYS:
        if k in src and target.get(k) != src[k]:
            target[k] = src[k]
            changed = True
    if src.get("completion_reasons") is not None:
        target["completion_reasons"] = src["completion_reasons"]
        changed = True
    target["completion_updated_at"] = now_iso()
    return changed


def main() -> int:
    js = load(JS_LATEST, {})
    by_h = by_handle_from_js(js)
    doc = {
        "generated_at": now_iso(),
        "timezone": "Asia/Shanghai",
        "source": str(JS_LATEST),
        "project_count": len(by_h),
        "high_completion_count": sum(1 for v in by_h.values() if v.get("high_completion")),
        "by_handle": by_h,
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # watchlist
    wl = load(WATCHLIST, {})
    wl_n = 0
    for p in wl.get("projects") or []:
        src = by_h.get(hkey(p.get("handle")))
        if not src:
            continue
        if apply_fields(p, src):
            wl_n += 1
    if wl.get("projects"):
        WATCHLIST.write_text(json.dumps(wl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # candidates
    cand = load(CANDIDATES, {})
    rows = cand.get("candidates") if isinstance(cand, dict) else None
    cand_n = 0
    if isinstance(rows, list):
        for c in rows:
            src = by_h.get(hkey(c.get("handle")))
            if not src:
                continue
            if apply_fields(c, src):
                cand_n += 1
        cand["completion_merged_at"] = now_iso()
        text = json.dumps(cand, ensure_ascii=False, indent=2) + "\n"
        CANDIDATES.write_text(text, encoding="utf-8")
        for m in MIRRORS:
            try:
                m.parent.mkdir(parents=True, exist_ok=True)
                m.write_text(text, encoding="utf-8")
            except Exception as e:
                print(f"WARN mirror {m}: {e}")

    print(
        f"[{now_iso()}] site_completion projects={len(by_h)} high={doc['high_completion_count']} "
        f"watchlist_updated={wl_n} candidates_updated={cand_n} -> {OUT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
