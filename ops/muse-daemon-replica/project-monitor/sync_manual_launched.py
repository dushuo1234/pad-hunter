#!/usr/bin/env python3
"""Pull Cloudflare 「手动确认已开盘」 marks → local removed_launched / Pages data.

Worker (api.adualpha.win) is source of truth for the tap. This script:
  1. GET /v1/launched/recent
  2. Soft-delete new handles into removed_launched.json (reason=manual, listing_at=null)
  3. Prune watchlist / candidates / projects / workbench + rebuild launched.json
  4. Optionally publish to GitHub Pages (main Contents API)
  5. Push full blocklist back to Worker (mode=replace; Worker unions manual marks)

Never invents listing_at. Token never printed. Network errors non-fatal in daemon mode.
Usage:
  sync_manual_launched.py [--once] [--publish] [--daemon] [--interval SEC]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launched_blocklist import (  # noqa: E402
    BASE,
    REMOVED,
    WORKBENCH,
    dump_json,
    hkey,
    load_blocklist,
    load_json,
    now_iso,
    prune_workbench,
)

URL_FILE = BASE / "workbench_api_public_url_cf.txt"
TOKEN_FILE = BASE / "workbench_api_token.txt"
STATE = BASE / "state" / "manual_launched_sync.json"
WATCHLIST = BASE / "watchlist.json"
DATA = Path("/workspace/push-radar/data")
CANDIDATES = DATA / "candidates.json"
PROJECTS = DATA / "projects.json"
LAUNCHED = DATA / "launched.json"
PUBLISH = Path("/workspace/publish-pages-data")
TIMEOUT = 15


def base_url() -> str:
    try:
        u = URL_FILE.read_text().strip().splitlines()[0].strip()
        if u.startswith("http"):
            return u.rstrip("/")
    except Exception:
        pass
    return "https://api.adualpha.win"


def call(method: str, path: str, body: dict | None = None) -> dict:
    tok = TOKEN_FILE.read_text().strip()
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(
        base_url() + path,
        data=data,
        method=method,
        headers={
            "X-Pad-Hunter-Token": tok,
            "Content-Type": "application/json",
            "User-Agent": "pad-hunter-box/sync_manual_launched",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def load_state() -> dict:
    return load_json(STATE, {"seen": {}, "last_run_at": None})


def save_state(st: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    dump_json(STATE, st)


def apply_manual_marks(items: list[dict]) -> dict:
    """Insert reason=manual entries; listing_at stays null (never invent)."""
    ts = now_iso()
    removed_doc = load_json(REMOVED, {"items": []})
    if isinstance(removed_doc, list):
        removed_doc = {"items": removed_doc}
    removed_items = removed_doc.setdefault("items", [])
    by_h = {hkey(e.get("handle")): e for e in removed_items if isinstance(e, dict)}

    wl = load_json(WATCHLIST, {})
    wl_by = {hkey(p.get("handle")): p for p in (wl.get("projects") or []) if isinstance(p, dict)}
    cand = load_json(CANDIDATES, {})
    cand_by = {
        hkey(c.get("handle")): c
        for c in (cand.get("candidates") or [])
        if isinstance(c, dict)
    }

    newly: list[dict] = []
    for raw in items or []:
        if not isinstance(raw, dict):
            continue
        handle = (raw.get("handle") or "").strip().lstrip("@")
        h = hkey(handle)
        if not h:
            continue
        reason = (raw.get("reason") or "manual").strip() or "manual"
        at = raw.get("at") or ts
        name = raw.get("name")
        existing = by_h.get(h)
        # Honor local restore; do not re-apply cloud manual for restored handles
        if existing and existing.get("restored"):
            continue
        if existing and not existing.get("restored") and (existing.get("reason") == reason or existing.get("launched_reason") == reason):
            continue
        snap = wl_by.get(h) or cand_by.get(h) or {}
        if existing:
            existing.update({
                "restored": False,
                "reason": reason,
                "launched_reason": reason,
                "evidence": existing.get("evidence") or "手动确认已开盘",
                "removed_at": at,
                "relaunched_at": at,
                "source": "cloud:manual",
            })
            # Do not invent listing_at; keep prior if any, else null
            if not existing.get("listing_at"):
                existing["listing_at"] = None
            if name and not existing.get("project"):
                existing["project"] = name
            newly.append(existing)
            continue
        entry = {
            "project": name or snap.get("name") or handle,
            "handle": snap.get("handle") or handle,
            "chain": snap.get("chain"),
            "category": snap.get("category"),
            "x_url": snap.get("x_url") or f"https://x.com/{handle}",
            "sites": snap.get("sites") or [],
            "listing_at": None,  # never invent
            "ca": snap.get("ca"),
            "ca_chain": snap.get("ca_chain"),
            "reason": reason,
            "launched_reason": reason,
            "evidence": "手动确认已开盘",
            "evidence_url": snap.get("x_url") or f"https://x.com/{handle}",
            "removed_at": at,
            "restored": False,
            "source": "cloud:manual",
            "snapshot": snap or None,
        }
        removed_items.append(entry)
        by_h[h] = entry
        newly.append(entry)

    if not newly and not items:
        return {"newly": 0, "handles": [], "at": ts}

    block = {hkey(e.get("handle")) for e in removed_items if isinstance(e, dict) and not e.get("restored")}
    removed_doc["updated_at"] = ts
    removed_doc["note"] = (
        "Soft-deleted launched projects. Handles here are a blocklist for "
        "watchlist/candidates/projects. Set restored=true to bring one back. "
        "reason=manual = website 手动确认已开盘."
    )
    dump_json(REMOVED, removed_doc)

    # watchlist
    projects = list(wl.get("projects") or [])
    before_w = len(projects)
    wl["projects"] = [p for p in projects if hkey(p.get("handle")) not in block]
    wl["count"] = len(wl["projects"])
    wl["last_prune_at"] = ts
    dump_json(WATCHLIST, wl)

    # candidates
    before_c = after_c = None
    if isinstance(cand, dict) and isinstance(cand.get("candidates"), list):
        before_c = len(cand["candidates"])
        cand["candidates"] = [c for c in cand["candidates"] if hkey(c.get("handle")) not in block]
        for i, c in enumerate(cand["candidates"], 1):
            c["rank"] = i
        after_c = len(cand["candidates"])
        cand["pruned_launched_at"] = ts
        dump_json(CANDIDATES, cand)

    # projects.json
    pj = load_json(PROJECTS, None)
    before_p = after_p = None
    if isinstance(pj, list):
        before_p = len(pj)
        pj = [x for x in pj if hkey(x.get("twitter_handle") or x.get("handle")) not in block]
        after_p = len(pj)
        dump_json(PROJECTS, pj)

    # launched.json
    latest: dict[str, dict] = {}
    for e in removed_items:
        if not isinstance(e, dict) or e.get("restored"):
            continue
        k = hkey(e.get("handle"))
        if k not in latest or (e.get("removed_at") or "") > (latest[k].get("removed_at") or ""):
            latest[k] = e
    items_out = sorted(latest.values(), key=lambda e: e.get("removed_at") or "", reverse=True)
    launched = {
        "generated_at": ts,
        "count": len(items_out),
        "items": [
            {
                k: e.get(k)
                for k in (
                    "project", "handle", "chain", "category", "x_url", "sites",
                    "listing_at", "ca", "ca_chain", "reason", "launched_reason",
                    "evidence", "evidence_url", "removed_at", "source",
                )
            }
            for e in items_out
        ],
    }
    dump_json(LAUNCHED, launched)

    # publish-pages-data mirror
    for name in ("candidates.json", "projects.json", "launched.json"):
        src = DATA / name
        if src.is_file():
            try:
                PUBLISH.mkdir(parents=True, exist_ok=True)
                PUBLISH.joinpath(name).write_bytes(src.read_bytes())
            except OSError as e:
                print(f"  WARN mirror {name}: {e}", flush=True)

    wb = prune_workbench(block)

    return {
        "newly": len(newly),
        "handles": [e.get("handle") for e in newly],
        "at": ts,
        "watchlist": f"{before_w}->{len(wl['projects'])}",
        "candidates": f"{before_c}->{after_c}",
        "projects": f"{before_p}->{after_p}",
        "launched_count": launched["count"],
        "workbench": f"{wb.get('before')}->{wb.get('after')}",
        "workbench_dropped": [d.get("handle") for d in (wb.get("dropped") or [])],
        "blocklist": len(block),
    }


def publish_site() -> int:
    from publish_pages_file import put_file

    rc = 0
    for local, remote, msg in (
        (LAUNCHED, "public/data/launched.json", "data: launched (manual sync)"),
        (CANDIDATES, "public/data/candidates.json", "data: candidates (manual sync)"),
        (PROJECTS, "public/data/projects.json", "data: projects (manual sync)"),
    ):
        if not local.is_file():
            continue
        try:
            put_file(local, remote, message=msg)
            print(f"  published {remote}", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"  WARN publish {remote}: {e}", flush=True)
            rc = 2
    return rc


def push_blocklist() -> dict:
    try:
        from cf_workbench_prune import run as _cf_run
        return _cf_run(mirror=True, push=True)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)[:200]}


def run_once(*, publish: bool) -> dict:
    out: dict = {"ok": True, "url": base_url(), "at": now_iso()}
    try:
        recent = call("GET", "/v1/launched/recent")
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        out.update(ok=False, error=f"{type(e).__name__}: {str(e)[:200]}")
        return out

    items = list(recent.get("items") or [])
    out["cloud_manual_count"] = recent.get("count")
    out["cloud_manual_updated_at"] = recent.get("updated_at")

    st = load_state()
    seen = st.setdefault("seen", {})
    fresh = []
    for it in items:
        if not isinstance(it, dict):
            continue
        h = hkey(it.get("handle"))
        at = it.get("at") or ""
        if not h:
            continue
        prev = seen.get(h)
        if prev == at:
            continue
        # also skip if already blocked locally with same reason
        fresh.append(it)

    applied = apply_manual_marks(fresh) if fresh else {
        "newly": 0, "handles": [], "at": now_iso(),
        "blocklist": len(load_blocklist()),
    }
    out["applied"] = applied

    for it in fresh:
        h = hkey(it.get("handle"))
        if h:
            seen[h] = it.get("at") or applied.get("at")
    st["last_run_at"] = out["at"]
    st["last_cloud_updated_at"] = recent.get("updated_at")
    save_state(st)

    # Always push blocklist so Worker stays aligned (replace ∪ manual)
    cf = push_blocklist()
    out["cf_workbench"] = {
        "ok": cf.get("ok"),
        "blocklist": cf.get("blocklist"),
        "worker_dropped": cf.get("worker_dropped"),
        "tombstoned": cf.get("tombstoned"),
        "error": cf.get("error"),
    }

    if publish and applied.get("newly", 0) > 0:
        out["publish_rc"] = publish_site()
    elif publish:
        # still republish if requested explicitly and files may have drifted
        out["publish_rc"] = publish_site()

    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", default=True)
    ap.add_argument("--daemon", action="store_true")
    ap.add_argument("--interval", type=int, default=45)
    ap.add_argument("--publish", action="store_true")
    args = ap.parse_args()
    if args.daemon:
        print(f"sync_manual_launched daemon interval={args.interval}s publish={args.publish}", flush=True)
        while True:
            try:
                res = run_once(publish=args.publish)
                if res.get("ok"):
                    a = res.get("applied") or {}
                    print(
                        f"sync_manual {res.get('at')} cloud={res.get('cloud_manual_count')} "
                        f"newly={a.get('newly')} handles={a.get('handles')} "
                        f"cf_ok={(res.get('cf_workbench') or {}).get('ok')}",
                        flush=True,
                    )
                else:
                    print(f"  WARN sync_manual failed: {res.get('error')}", flush=True)
            except Exception as e:  # noqa: BLE001
                print(f"  WARN sync_manual exception: {e}", flush=True)
            time.sleep(max(15, args.interval))
    res = run_once(publish=args.publish)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
