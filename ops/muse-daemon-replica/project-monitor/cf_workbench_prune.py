#!/usr/bin/env python3
"""Keep the Cloudflare workbench (https://api.adualpha.win) in sync with box launched rules.

1. Push the launched blocklist (removed_launched.json restored=false + launched.json)
   to POST /v1/workbench/blocklist. The Worker stores it, drops+tombstones any
   blocked pin, broadcasts over WS, and rejects future re-adds of those handles.
2. Belt-and-braces: GET pins; any still-blocked handle → POST /v1/workbench/sync
   with removed:[{handle, removed_at:now}].
3. Mirror cloud pins → local workbench_active.json (same file format) so
   fast_site_poll / 开盘与CA预警 still see what the user pinned on the site.

Never raises on network errors (exit 0, prints WARN). Token never printed.
Usage: cf_workbench_prune.py [--mirror-only] [--no-mirror]
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from launched_blocklist import BASE, WORKBENCH, dump_json, hkey, load_blocklist, load_json, now_iso  # noqa: E402

URL_FILE = BASE / "workbench_api_public_url_cf.txt"
TOKEN_FILE = BASE / "workbench_api_token.txt"
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
        base_url() + path, data=data, method=method,
        headers={"X-Pad-Hunter-Token": tok, "Content-Type": "application/json",
                 "User-Agent": "pad-hunter-box/cf_workbench_prune"},
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())


def mirror_local(pins: dict, block: set[str]) -> dict:
    """Cloud pins → local workbench_active.json (format preserved)."""
    prev = load_json(WORKBENCH, {}) or {}
    items = [it for it in (pins.get("items") or []) if isinstance(it, dict) and hkey(it.get("handle")) not in block]
    before = [it.get("handle") for it in prev.get("items") or [] if isinstance(it, dict)]
    after = [it.get("handle") for it in items]
    if before == after and (prev.get("items") or []) == items:
        return {"changed": False, "count": len(items)}
    doc = dict(prev)
    doc.update({
        "synced_at": pins.get("synced_at") or now_iso(),
        "timezone": "Asia/Shanghai",
        "client_id": "cloud-mirror",
        "count": len(items),
        "items": items,
        "removed": pins.get("removed") or [],
        "source": base_url(),
        "mirrored_at": now_iso(),
    })
    doc.setdefault("dropped_launched", [])
    dump_json(WORKBENCH, doc)
    return {"changed": True, "count": len(items), "before": before, "after": after}


def run(mirror: bool = True, push: bool = True) -> dict:
    out: dict = {"ok": True, "url": base_url(), "at": now_iso()}
    block = load_blocklist()
    out["blocklist"] = len(block)
    try:
        if push:
            r = call("POST", "/v1/workbench/blocklist",
                     {"handles": sorted(block), "source": "box:removed_launched+launched.json", "mode": "replace"})
            out["worker_dropped"] = [d.get("handle") for d in r.get("dropped_launched") or []]
        pins = call("GET", "/v1/workbench/pins")
        stale = [it.get("handle") for it in pins.get("items") or [] if hkey(it.get("handle")) in block]
        if stale:
            ts = now_iso()
            pins = call("POST", "/v1/workbench/sync", {
                "client_id": "box-launched-prune", "items": [],
                "removed": [{"handle": h, "removed_at": ts} for h in stale]})
        out["tombstoned"] = stale
        out["cloud_pins"] = [it.get("handle") for it in pins.get("items") or []]
        if mirror:
            out["mirror"] = mirror_local(pins, block)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as e:
        out.update(ok=False, error=f"{type(e).__name__}: {str(e)[:200]}")
    return out


def main() -> int:
    args = set(sys.argv[1:])
    res = run(mirror="--no-mirror" not in args, push="--mirror-only" not in args)
    if res.get("ok"):
        print(f"cf_workbench {res['at']} blocklist={res['blocklist']} "
              f"worker_dropped={res.get('worker_dropped', [])} tombstoned={res.get('tombstoned')} "
              f"cloud_pins={res.get('cloud_pins')} mirror={ {k: v for k, v in (res.get('mirror') or {}).items() if k in ('changed', 'count')} }")
    else:
        print(f"  WARN cf_workbench sync failed (non-fatal): {res.get('error')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
