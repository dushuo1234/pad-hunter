#!/usr/bin/env python3
"""Pad Hunter workbench realtime API (Sentinel-style, workbench-only scanning).

Runs on 127.0.0.1:8780 behind a public tunnel (see workbench_api_daemon.sh).
The static GitHub Pages site syncs the browser workbench (localStorage
`pad-hunter.workbench.v1`) here; fast_site_poll.py then polls only those sites at ~1s
and drains workbench_check_queue.jsonl for manual 「检查」 requests.

v1.4.0: multi-device merge sync for pins (LWW + tombstones) and reviewed marks.
v1.5.0: realtime WebSocket push at /v1/workbench/ws (broadcast pins/reviewed changes).

Auth: header X-Pad-Hunter-Token == workbench_api_token.txt (never committed).
/health is public (no secrets) so the site can show "API online".
Also receives Helius Solana webhooks at POST /hooks/helius/solana.
All timestamps Asia/Shanghai.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import secrets
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

VERSION = "1.5.0"
BASE = Path("/workspace/project-monitor")
TOKEN_PATH = BASE / "workbench_api_token.txt"
WORKBENCH_PATH = BASE / "workbench_active.json"
REVIEWED_PATH = BASE / "workbench_reviewed.json"
CHECK_QUEUE_PATH = BASE / "workbench_check_queue.jsonl"
STATE_PATH = BASE / "fast_site_state.json"
ALERTS_PATH = BASE / "fast_site_alerts.jsonl"
POLL_PID = BASE / "fast_site_poll.pid"
WATCHLIST = BASE / "watchlist.json"
LISTING_TIMES = BASE / "listing_times.json"
CA_FINDS = BASE / "ca_finds.json"
RADAR_DIR = Path("/workspace/push-radar/data")
RADAR_CANDIDATES = RADAR_DIR / "candidates.json"
RADAR_PROJECTS = RADAR_DIR / "projects.json"
RADAR_LAUNCHED = RADAR_DIR / "launched.json"
TG_FAST_STATE = BASE / "tg_push_fast_state.json"
PUBLIC_URL_PATH = BASE / "workbench_api_public_url.txt"
SH = ZoneInfo("Asia/Shanghai")
WRITE_LOCK = threading.Lock()
QUEUED: dict[str, float] = {}       # handle -> epoch queued (API side, for instant "checking")
CHECK_MIN_GAP = 3.0                 # per-handle manual check debounce
TOMBSTONE_MAX = 500
TOMBSTONE_DAYS = 30


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def norm(h: Optional[str]) -> str:
    return (h or "").strip().lstrip("@").strip().lower()


def load_json(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json_atomic(p: Path, obj) -> None:
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)


def get_token() -> str:
    if not TOKEN_PATH.exists() or not TOKEN_PATH.read_text().strip():
        TOKEN_PATH.write_text(secrets.token_urlsafe(32) + "\n")
        os.chmod(TOKEN_PATH, 0o600)
    return TOKEN_PATH.read_text().strip()


TOKEN = get_token()


def require_token(x_pad_hunter_token: Optional[str] = Header(default=None)) -> None:
    if not x_pad_hunter_token or not secrets.compare_digest(x_pad_hunter_token.strip(), TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing X-Pad-Hunter-Token")


def poller_alive() -> bool:
    try:
        pid = POLL_PID.read_text().strip()
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().decode(errors="ignore")
        return "fast_site_poll.py" in cmd
    except Exception:
        return False


ORIGIN_RE = r"^(https://dushuo1234\.github\.io|https?://(localhost|127\.0\.0\.1)(:\d+)?|null)$"
app = FastAPI(title="Pad Hunter Workbench API", version=VERSION, docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=ORIGIN_RE,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-Pad-Hunter-Token", "Content-Type", "ngrok-skip-browser-warning"],
    expose_headers=["X-Pad-Hunter-Version"],
    allow_credentials=False,
    max_age=600,
)


@app.middleware("http")
async def version_header(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Pad-Hunter-Version"] = VERSION
    resp.headers["Cache-Control"] = "no-store"
    return resp


class WBItem(BaseModel):
    handle: str = Field(min_length=1, max_length=64)
    name: Optional[str] = Field(default=None, max_length=200)
    sites: Optional[list[str]] = Field(default=None, max_length=20)
    x_url: Optional[str] = Field(default=None, max_length=300)
    chain: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=2000)
    push: Optional[bool] = True
    added_at: Optional[str] = Field(default=None, max_length=64)
    updated_at: Optional[str] = Field(default=None, max_length=64)


class RemovedTombstone(BaseModel):
    handle: str = Field(min_length=1, max_length=64)
    removed_at: Optional[str] = Field(default=None, max_length=64)


class SyncBody(BaseModel):
    items: list[WBItem] = Field(default_factory=list, max_length=300)
    client_id: Optional[str] = Field(default=None, max_length=128)
    # None = legacy client (field omitted) → merge add/update only, never wipe via absence.
    # Present (even []) → apply tombstone LWW.
    removed: Optional[list[RemovedTombstone]] = Field(default=None, max_length=500)


class CheckBody(BaseModel):
    handle: str = Field(min_length=1, max_length=64)


class ReviewedMark(BaseModel):
    at: Optional[str] = Field(default=None, max_length=64)
    snapshot: Optional[Any] = None
    cleared_at: Optional[str] = Field(default=None, max_length=64)


class ReviewedSyncBody(BaseModel):
    client_id: Optional[str] = Field(default=None, max_length=128)
    marks: dict[str, ReviewedMark] = Field(default_factory=dict)


def workbench() -> dict:
    doc = load_json(WORKBENCH_PATH, {"items": [], "removed": []}) or {"items": [], "removed": []}
    if "items" not in doc or not isinstance(doc.get("items"), list):
        doc["items"] = []
    if "removed" not in doc or not isinstance(doc.get("removed"), list):
        doc["removed"] = []
    return doc


def listing_lookup() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for it in (load_json(LISTING_TIMES, {}) or {}).get("items") or []:
        if it.get("handle"):
            out[norm(it["handle"])] = it
    return out


def watch_lookup() -> dict[str, dict]:
    return {norm(p.get("handle")): p for p in (load_json(WATCHLIST, {}).get("projects") or []) if p.get("handle")}


def pending_queue_handles() -> set[str]:
    hs = set()
    for p in (CHECK_QUEUE_PATH, CHECK_QUEUE_PATH.with_suffix(".processing")):
        try:
            for ln in p.read_text(encoding="utf-8").splitlines():
                try:
                    hs.add(norm(json.loads(ln).get("handle")))
                except Exception:
                    pass
        except FileNotFoundError:
            pass
    return hs


def site_status(s: dict) -> str:
    if not s or not s.get("last_probe_at"):
        return "unknown"
    if s.get("last_error") or s.get("error_streak"):
        return "down"
    code = str(s.get("http_code") or "")
    if code.isdigit() and 200 <= int(code) < 400:
        return "up"
    return "unknown"


def epoch(iso: Optional[str]) -> float:
    try:
        return datetime.fromisoformat(iso).timestamp() if iso else 0.0
    except Exception:
        return 0.0


def item_effective_ts(it: dict, default_iso: Optional[str] = None) -> float:
    """updated_at, else added_at, else default (usually now)."""
    return epoch(it.get("updated_at") or it.get("added_at") or default_iso)


def prune_tombstones(removed: list[dict]) -> list[dict]:
    """Dedupe by handle (newest removed_at), drop older than 30d, keep last ~500."""
    by_h: dict[str, dict] = {}
    for t in removed or []:
        if not isinstance(t, dict):
            continue
        h = norm(t.get("handle"))
        if not h:
            continue
        ra = t.get("removed_at") or ""
        prev = by_h.get(h)
        if not prev or ra > (prev.get("removed_at") or ""):
            by_h[h] = {"handle": (t.get("handle") or h).strip().lstrip("@"), "removed_at": ra}
    cutoff = (datetime.now(SH) - timedelta(days=TOMBSTONE_DAYS)).timestamp()
    kept = []
    for t in by_h.values():
        ts = epoch(t.get("removed_at"))
        if ts == 0.0 or ts >= cutoff:
            kept.append(t)
    kept.sort(key=lambda x: x.get("removed_at") or "", reverse=True)
    return kept[:TOMBSTONE_MAX]


def pins_payload(wb: dict) -> dict:
    return {
        "synced_at": wb.get("synced_at") or now_iso(),
        "items": list(wb.get("items") or []),
        "removed": list(wb.get("removed") or []),
    }


def merge_workbench(prev: dict, body: SyncBody, blocked: set[str]) -> tuple[dict, list[dict]]:
    """Merge incoming pins + optional tombstones into prev (LWW by handle)."""
    now = now_iso()
    items_by: dict[str, dict] = {}
    for it in prev.get("items") or []:
        if not isinstance(it, dict):
            continue
        h = norm(it.get("handle"))
        if h:
            items_by[h] = dict(it)
    tombs_by: dict[str, dict] = {}
    for t in prev.get("removed") or []:
        if not isinstance(t, dict):
            continue
        h = norm(t.get("handle"))
        if h:
            tombs_by[h] = {
                "handle": (t.get("handle") or h).strip().lstrip("@"),
                "removed_at": t.get("removed_at") or now,
            }

    dropped: list[dict] = []

    for it in body.items:
        h = norm(it.handle)
        if not h:
            continue
        display = it.handle.strip().lstrip("@")
        if h in blocked:
            dropped.append({"handle": display, "name": it.name})
            continue
        d = it.model_dump()
        d["handle"] = display
        d["sites"] = [u.strip() for u in (it.sites or []) if isinstance(u, str) and u.strip()][:20]
        existing = items_by.get(h)
        # effective incoming timestamp
        inc_iso = d.get("updated_at") or d.get("added_at") or now
        if not d.get("updated_at"):
            d["updated_at"] = inc_iso
        if not d.get("added_at"):
            d["added_at"] = (existing.get("added_at") if existing else None) or now
        inc_ts = epoch(d.get("updated_at") or d.get("added_at"))

        tomb = tombs_by.get(h)
        if tomb and epoch(tomb.get("removed_at")) >= inc_ts:
            # tombstone wins — do not resurrect
            continue
        if tomb and inc_ts > epoch(tomb.get("removed_at")):
            tombs_by.pop(h, None)

        if existing:
            ex_ts = item_effective_ts(existing)
            if inc_ts < ex_ts:
                continue
            # preserve earliest added_at
            if existing.get("added_at"):
                if not d.get("added_at") or epoch(existing["added_at"]) <= epoch(d.get("added_at")):
                    d["added_at"] = existing["added_at"]
            # coalesce: keep existing non-empty fields when incoming sends null/empty
            for fld in ("name", "sites", "x_url", "chain", "notes"):
                inv = d.get(fld)
                exv = existing.get(fld)
                if inv is None or inv == "" or inv == []:
                    if exv not in (None, "", []):
                        d[fld] = exv
        items_by[h] = d

    if body.removed is not None:
        for t in body.removed:
            h = norm(t.handle)
            if not h:
                continue
            display = t.handle.strip().lstrip("@")
            ra = t.removed_at or now
            ra_ts = epoch(ra)
            existing = items_by.get(h)
            if existing:
                if ra_ts > item_effective_ts(existing, now):
                    items_by.pop(h, None)
                    tombs_by[h] = {"handle": display, "removed_at": ra}
                # else item newer/equal → keep item, ignore older tombstone
            else:
                prev_t = tombs_by.get(h)
                if not prev_t or ra_ts >= epoch(prev_t.get("removed_at")):
                    tombs_by[h] = {"handle": display, "removed_at": ra}

    # Drop any remaining blocklisted items (defense in depth)
    for h in list(items_by.keys()):
        if h in blocked:
            it = items_by.pop(h)
            dropped.append({"handle": it.get("handle"), "name": it.get("name")})

    items_list = list(items_by.values())
    items_list.sort(key=lambda x: x.get("added_at") or "")
    removed_list = prune_tombstones(list(tombs_by.values()))
    note = prev.get("note") or (
        "Realtime poller (fast_site_poll.py) polls only these sites; the 30-min "
        "listing/onchain/js pipeline still scans the full watchlist. "
        "Launched (removed_launched blocklist) handles are rejected on sync."
    )
    doc = {
        "synced_at": now,
        "timezone": "Asia/Shanghai",
        "client_id": body.client_id,
        "count": len(items_list),
        "items": items_list,
        "removed": removed_list,
        "dropped_launched": dropped,
        "note": note,
    }
    return doc, dropped


def reviewed_doc() -> dict:
    doc = load_json(REVIEWED_PATH, None)
    if not isinstance(doc, dict):
        doc = {"synced_at": now_iso(), "timezone": "Asia/Shanghai", "marks": {}}
        write_json_atomic(REVIEWED_PATH, doc)
    if "marks" not in doc or not isinstance(doc.get("marks"), dict):
        doc["marks"] = {}
    return doc


def norm_review_key(key: str) -> str:
    """Handles → lowercase-trim; name:... keys stored as given (trimmed)."""
    k = (key or "").strip()
    if k.lower().startswith("name:"):
        # keep original casing after normalizing the prefix spelling
        return "name:" + k.split(":", 1)[1]
    return norm(k)


def mark_effective_ts(m: dict) -> float:
    """LWW key = max(at, cleared_at); missing/null → 0."""
    return max(epoch(m.get("at")), epoch(m.get("cleared_at")))


def merge_reviewed(prev: dict, body: ReviewedSyncBody) -> dict:
    now = now_iso()
    marks: dict[str, dict] = {}
    for k, v in (prev.get("marks") or {}).items():
        if isinstance(v, dict):
            marks[k] = dict(v)
    for raw_k, mark in (body.marks or {}).items():
        k = norm_review_key(raw_k)
        if not k:
            continue
        incoming = mark.model_dump() if hasattr(mark, "model_dump") else dict(mark)
        # drop None-only noise but keep explicit nulls for cleared_at/at as absent
        clean = {
            "at": incoming.get("at"),
            "snapshot": incoming.get("snapshot"),
            "cleared_at": incoming.get("cleared_at"),
        }
        existing = marks.get(k)
        if existing is None or mark_effective_ts(clean) >= mark_effective_ts(existing):
            marks[k] = clean
    return {
        "synced_at": now,
        "timezone": "Asia/Shanghai",
        "client_id": body.client_id,
        "marks": marks,
    }


def is_checking(h: str, s: dict, pend: set[str]) -> bool:
    if s.get("checking") or h in pend:
        return True
    q = QUEUED.get(h)
    if q and time.time() - q < 120 and epoch(s.get("last_manual_check_at")) < q - 1:
        return True
    return False


def ca_for(h: str) -> list[dict]:
    doc = load_json(CA_FINDS, {}) or {}
    rows = doc.get("finds") or doc.get("items") or []
    return [r for r in rows if norm(r.get("handle")) == h][:20]


def build_row(it: dict, sites: dict, lt: dict, wl: dict, st: dict, pend: set[str]) -> dict:
    h = norm(it.get("handle"))
    s = sites.get(h) or {}
    wp = wl.get(h) or {}
    li = lt.get(h) or {}
    listing_at = li.get("listing_at") or wp.get("listing_at") or None
    addrs = s.get("last_addrs") or []
    return {
        "handle": it.get("handle"),
        "name": it.get("name") or s.get("name") or wp.get("name") or it.get("handle"),
        "url": s.get("site") or next((u for u in (it.get("sites") or wp.get("sites") or []) if "x.com" not in u and "twitter.com" not in u), None),
        "polled": h in set(st.get("workbench_handles") or []) and st.get("target_mode") == "workbench",
        "site_status": site_status(s),
        "http_code": s.get("http_code"),
        "last_error": s.get("last_error"),
        "last_check_at": s.get("last_probe_at"),
        "last_latency_ms": s.get("last_latency_ms"),
        "interval_s": s.get("interval_s") or st.get("poll_interval_s"),
        "change_count": int(s.get("change_count") or 0),
        "last_change_at": s.get("last_change_at"),
        "address_count": len(addrs),
        "last_addresses": [{"type": a.get("type"), "address": a.get("address"), "source": a.get("source")} for a in addrs[:5]],
        "low_confidence": bool(s.get("low_confidence")),
        "push": it.get("push", True) is not False,
        "listing_at": listing_at or "未知",
        "listing_source": li.get("source") or None,
        "listing_evidence_url": li.get("evidence_url") or None,
        "already_listed": bool(li.get("already_listed")),
        "checking": is_checking(h, s, pend),
        "last_manual_check_at": s.get("last_manual_check_at"),
        "last_manual_result": s.get("last_manual_result"),
    }


def _helius_secret_ok(secret_q: Optional[str], authorization: Optional[str]) -> bool:
    """Accept ?secret= or Authorization: Bearer <secret> (Helius authHeader)."""
    try:
        from solana_helius_hook import get_webhook_secret
        expected = get_webhook_secret()
    except Exception:
        return False
    if not expected:
        return False
    if secret_q and secrets.compare_digest(secret_q.strip(), expected):
        return True
    if authorization:
        raw = authorization.strip()
        if raw.lower().startswith("bearer "):
            raw = raw[7:].strip()
        if secrets.compare_digest(raw, expected):
            return True
    return False


@app.post("/hooks/helius/solana")
async def helius_solana_hook(
    request: Request,
    secret: Optional[str] = Query(default=None),
    authorization: Optional[str] = Header(default=None),
    x_pad_hunter_synthetic: Optional[str] = Header(default=None),
):
    """Helius -> Pad Hunter Solana launch watcher (workbench-gated).

    Auth: query ?secret= OR Authorization bearer matching .helius_webhook_secret.
    Does not use X-Pad-Hunter-Token (Helius sets authHeader only).
    Under solana_scan_pref mode=workbench_only, payloads are ignored unless
    workbench_active has Solana items (mass Pump webhook should stay deleted).
    """
    if not _helius_secret_ok(secret, authorization):
        raise HTTPException(status_code=401, detail="invalid webhook secret")
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid json")
    synthetic = (x_pad_hunter_synthetic or "").strip() in ("1", "true", "yes")
    try:
        from solana_helius_hook import process_payload
        stats = process_payload(payload, synthetic=synthetic)
    except Exception as e:
        with (BASE / "helius_webhook_errors.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": now_iso(), "error": str(e)[:300]}, ensure_ascii=False) + "\n")
        return {"ok": False, "error": "processing_failed"}
    return {"ok": True, **stats}


# ---------------------------------------------------------------- realtime WS hub
WS_KEEPALIVE_S = 20.0
WS_AUTH_TIMEOUT_S = 5.0
FILE_WATCH_S = 1.0
LOOP: Optional[asyncio.AbstractEventLoop] = None
CLIENTS: dict[WebSocket, asyncio.Lock] = {}
KNOWN_MTIME: dict[str, int] = {}   # path -> mtime_ns of our own last write / last broadcast


def _mtime(p: Path) -> int:
    try:
        return p.stat().st_mtime_ns
    except FileNotFoundError:
        return 0


def pins_state() -> dict:
    return pins_payload(workbench())


def reviewed_state() -> dict:
    with WRITE_LOCK:
        doc = reviewed_doc()
    return {"synced_at": doc.get("synced_at") or now_iso(), "marks": doc.get("marks") or {}}


async def _send(ws: WebSocket, lock: asyncio.Lock, msg: dict) -> bool:
    try:
        async with lock:
            await asyncio.wait_for(ws.send_text(json.dumps(msg, ensure_ascii=False)), timeout=10)
        return True
    except Exception:
        return False


async def broadcast(msg: dict) -> None:
    items = list(CLIENTS.items())
    if not items:
        return
    res = await asyncio.gather(*[_send(ws, lk, msg) for ws, lk in items])
    for (ws, _), ok in zip(items, res):
        if not ok:
            CLIENTS.pop(ws, None)


def notify_from_thread(kind: str, state: dict, origin: Optional[str]) -> None:
    """Called after a successful write (any thread). Marks mtime known + schedules broadcast."""
    path = WORKBENCH_PATH if kind == "pins" else REVIEWED_PATH
    KNOWN_MTIME[str(path)] = _mtime(path)
    msg = {"type": kind, "state": state, "origin_client_id": origin}
    if LOOP is None:
        return
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is LOOP:
        LOOP.create_task(broadcast(msg))
    else:
        asyncio.run_coroutine_threadsafe(broadcast(msg), LOOP)


async def _file_watcher() -> None:
    """Out-of-process edits (prune_launched.py, mark_launched_from_ca.py, ...) → broadcast."""
    for p in (WORKBENCH_PATH, REVIEWED_PATH):
        KNOWN_MTIME.setdefault(str(p), _mtime(p))
    while True:
        await asyncio.sleep(FILE_WATCH_S)
        try:
            for kind, p in (("pins", WORKBENCH_PATH), ("reviewed", REVIEWED_PATH)):
                m = _mtime(p)
                if m and m != KNOWN_MTIME.get(str(p)):
                    KNOWN_MTIME[str(p)] = m
                    if CLIENTS:
                        state = await run_in_threadpool(pins_state if kind == "pins" else reviewed_state)
                        await broadcast({"type": kind, "state": state, "origin_client_id": None,
                                         "source": "file_watch"})
        except Exception:
            pass


async def _keepalive() -> None:
    while True:
        await asyncio.sleep(WS_KEEPALIVE_S)
        if CLIENTS:
            await broadcast({"type": "ping", "server_time": now_iso()})


@app.on_event("startup")
async def _ws_startup() -> None:
    global LOOP
    LOOP = asyncio.get_running_loop()
    LOOP.create_task(_file_watcher())
    LOOP.create_task(_keepalive())


def _token_ok(tok: Optional[str]) -> bool:
    return bool(tok) and secrets.compare_digest(tok.strip(), TOKEN)


@app.websocket("/v1/workbench/ws")
async def workbench_ws(ws: WebSocket, token: Optional[str] = Query(default=None)):
    origin = ws.headers.get("origin")
    if origin is not None and not re.match(ORIGIN_RE, origin):
        await ws.close(code=4403)  # pre-accept close → HTTP 403
        return
    # token: ?token=  |  Sec-WebSocket-Protocol (raw token or "token.<t>"/"bearer.<t>")  |  first {type:auth}
    subproto = None
    authed = _token_ok(token)
    if not authed:
        offered = [s.strip() for s in (ws.headers.get("sec-websocket-protocol") or "").split(",") if s.strip()]
        for s in offered:
            cand = s.split(".", 1)[1] if s.lower().startswith(("token.", "bearer.")) else s
            if _token_ok(cand):
                authed, subproto = True, s
                break
    await ws.accept(subprotocol=subproto)
    if not authed and token:
        await ws.close(code=4401, reason="invalid token")
        return
    if not authed:
        try:
            raw = await asyncio.wait_for(ws.receive_text(), timeout=WS_AUTH_TIMEOUT_S)
            m = json.loads(raw)
            authed = isinstance(m, dict) and m.get("type") == "auth" and _token_ok(m.get("token"))
        except Exception:
            authed = False
        if not authed:
            await ws.close(code=4401, reason="invalid token")
            return
    lock = asyncio.Lock()
    CLIENTS[ws] = lock
    try:
        await _send(ws, lock, {"type": "hello", "version": VERSION, "server_time": now_iso()})
        await _send(ws, lock, {"type": "pins", "state": await run_in_threadpool(pins_state), "origin_client_id": None})
        await _send(ws, lock, {"type": "reviewed", "state": await run_in_threadpool(reviewed_state), "origin_client_id": None})
        while True:
            raw = await ws.receive_text()
            try:
                m = json.loads(raw)
            except Exception:
                await _send(ws, lock, {"type": "error", "error": "invalid json"})
                continue
            typ = m.get("type") if isinstance(m, dict) else None
            if typ == "ping":
                await _send(ws, lock, {"type": "pong", "server_time": now_iso()})
            elif typ == "pong" or typ == "auth":
                continue
            elif typ == "pins_sync":
                try:
                    body = SyncBody.model_validate(m.get("body") or {})
                except Exception as e:
                    await _send(ws, lock, {"type": "error", "op": "pins_sync", "error": str(e)[:300]})
                    continue
                await run_in_threadpool(do_pins_sync, body)
            elif typ == "reviewed_sync":
                try:
                    body = ReviewedSyncBody.model_validate(m.get("body") or {})
                except Exception as e:
                    await _send(ws, lock, {"type": "error", "op": "reviewed_sync", "error": str(e)[:300]})
                    continue
                await run_in_threadpool(do_reviewed_sync, body)
            else:
                await _send(ws, lock, {"type": "error", "error": f"unknown type {typ!r}"})
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        CLIENTS.pop(ws, None)


@app.get("/health")
def health():
    wb = workbench()
    st = load_json(STATE_PATH, {}) or {}
    return {
        "ok": True, "version": VERSION, "now": now_iso(),
        "workbench_count": len(wb.get("items") or []),
        "poller_alive": poller_alive(),
        "poller_target_mode": st.get("target_mode"),
        "poller_updated_at": st.get("updated_at"),
        "ws_clients": len(CLIENTS),
    }


def _reconcile_solana_webhook() -> dict:
    """Best-effort: keep Helius Solana webhook scoped to workbench Solana pins.
    Never fails the sync endpoint — returns {ok, ...} or {ok:False, error}.
    """
    try:
        from solana_helius_setup import cmd_ensure
        code = cmd_ensure(force_mass=False)
        return {"ok": code == 0, "exit": code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


@app.get("/v1/workbench/pins", dependencies=[Depends(require_token)])
def get_pins():
    """Cloud pin list + tombstones for multi-device merge."""
    return pins_payload(workbench())


def do_pins_sync(body: SyncBody) -> dict:
    """Merge pins (LWW) + optional tombstones. Legacy bodies without `removed` never wipe."""
    try:
        from launched_blocklist import load_blocklist
        blocked = load_blocklist()
    except Exception:
        blocked = set()
    with WRITE_LOCK:
        prev = workbench()
        doc, dropped = merge_workbench(prev, body, blocked)
        write_json_atomic(WORKBENCH_PATH, doc)
        KNOWN_MTIME[str(WORKBENCH_PATH)] = _mtime(WORKBENCH_PATH)
    notify_from_thread("pins", pins_payload(doc), body.client_id)
    solana_wh = _reconcile_solana_webhook()
    out = pins_payload(doc)
    out["ok"] = True
    out["count"] = doc["count"]
    out["dropped_launched"] = dropped
    out["solana_webhook"] = solana_wh
    return out


@app.post("/v1/workbench/sync", dependencies=[Depends(require_token)])
def sync(body: SyncBody):
    return do_pins_sync(body)


@app.get("/v1/workbench/reviewed", dependencies=[Depends(require_token)])
def get_reviewed():
    """Cloud 「已看」 marks for multi-device sync."""
    with WRITE_LOCK:
        doc = reviewed_doc()
    return {
        "synced_at": doc.get("synced_at") or now_iso(),
        "marks": doc.get("marks") or {},
    }


def do_reviewed_sync(body: ReviewedSyncBody) -> dict:
    """Per-key LWW on max(at, cleared_at)."""
    with WRITE_LOCK:
        prev = reviewed_doc()
        doc = merge_reviewed(prev, body)
        write_json_atomic(REVIEWED_PATH, doc)
        KNOWN_MTIME[str(REVIEWED_PATH)] = _mtime(REVIEWED_PATH)
    state = {"synced_at": doc["synced_at"], "marks": doc.get("marks") or {}}
    notify_from_thread("reviewed", state, body.client_id)
    return state


@app.post("/v1/workbench/reviewed/sync", dependencies=[Depends(require_token)])
def sync_reviewed(body: ReviewedSyncBody):
    return do_reviewed_sync(body)


@app.get("/v1/workbench/status", dependencies=[Depends(require_token)])
def status():
    wb = workbench()
    st = load_json(STATE_PATH, {}) or {}
    sites = {norm(k): v for k, v in (st.get("sites") or {}).items()}
    lt, wl, pend = listing_lookup(), watch_lookup(), pending_queue_handles()
    rows = [build_row(it, sites, lt, wl, st, pend) for it in wb.get("items") or []]
    return {
        "now": now_iso(),
        "synced_at": wb.get("synced_at"),
        "poller": {
            "alive": poller_alive(),
            "target_mode": st.get("target_mode"),
            "watched_count": st.get("watched_count"),
            "poll_interval_s": st.get("poll_interval_s"),
            "updated_at": st.get("updated_at"),
            "last_cycle": st.get("last_cycle"),
        },
        "count": len(rows),
        "items": rows,
    }


@app.post("/v1/workbench/check", dependencies=[Depends(require_token)])
def check(body: CheckBody):
    h = norm(body.handle)
    if not h:
        raise HTTPException(400, "handle required")
    now = time.time()
    if now - QUEUED.get(h, 0) < CHECK_MIN_GAP:
        return {"queued": True, "deduped": True, "handle": body.handle}
    QUEUED[h] = now
    req = {"handle": body.handle.strip().lstrip("@"), "requested_at": now_iso(), "source": "workbench_api"}
    with WRITE_LOCK:
        with CHECK_QUEUE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(req, ensure_ascii=False) + "\n")
    return {"queued": True, "handle": req["handle"], "requested_at": req["requested_at"],
            "poller_alive": poller_alive()}


@app.get("/v1/workbench/detail", dependencies=[Depends(require_token)])
def detail(handle: str = Query(min_length=1, max_length=64)):
    h = norm(handle)
    wb = workbench()
    it = next((x for x in wb.get("items") or [] if norm(x.get("handle")) == h), {"handle": handle})
    st = load_json(STATE_PATH, {}) or {}
    sites = {norm(k): v for k, v in (st.get("sites") or {}).items()}
    s = sites.get(h) or {}
    row = build_row(it, sites, listing_lookup(), watch_lookup(), st, pending_queue_handles())
    alerts = []
    try:
        for ln in ALERTS_PATH.read_text(encoding="utf-8").splitlines():
            try:
                ev = json.loads(ln)
            except Exception:
                continue
            if norm(ev.get("handle")) == h:
                alerts.append({k: ev.get(k) for k in ("type", "at", "site", "address", "addr_type", "source",
                                                      "confidence", "reason", "address_count", "note")})
    except FileNotFoundError:
        pass
    changes = list(s.get("recent_changes") or [])
    changes += [{"at": a["at"], "kind": a["type"], **{k: v for k, v in a.items() if k not in ("at", "type") and v is not None}} for a in alerts]
    changes.sort(key=lambda x: x.get("at") or "", reverse=True)
    history = list(reversed(s.get("history") or []))[:100]
    return {
        "now": now_iso(),
        "item": row,
        "workbench_item": it,
        "addresses": s.get("last_addrs") or [],
        "ca_finds": ca_for(h),
        "recent_changes": changes[:30],
        "crawl_history": history,
        "crawl_history_note": None if history else "no per-probe history yet (poller records it for polled sites)",
        "last_full_at": s.get("last_full_at"),
        "full_extract_cooldown_s": s.get("full_extract_cooldown_s"),
    }


@app.get("/v1/radar/candidates")
def radar_candidates():
    """Public live candidates for the Pages SPA (no token). Fresh from box disk."""
    doc = load_json(RADAR_CANDIDATES, None)
    if doc is None:
        raise HTTPException(status_code=503, detail="candidates unavailable")
    # Soft wrap so clients can see sync freshness
    if isinstance(doc, dict):
        st = load_json(TG_FAST_STATE, {}) or {}
        doc = {
            **doc,
            "live_at": now_iso(),
            "live_source": "workbench_api",
            "tg_fast_at": st.get("at"),
            "tg_fast_added": st.get("added") or [],
        }
    return doc


@app.get("/v1/radar/projects")
def radar_projects():
    doc = load_json(RADAR_PROJECTS, None)
    if doc is None:
        raise HTTPException(status_code=503, detail="projects unavailable")
    return doc


@app.get("/v1/radar/launched")
def radar_launched():
    doc = load_json(RADAR_LAUNCHED, None)
    if doc is None:
        raise HTTPException(status_code=503, detail="launched unavailable")
    return doc


@app.get("/v1/radar/meta")
def radar_meta():
    """Cheap freshness probe for SPA polling (no token)."""
    st = load_json(TG_FAST_STATE, {}) or {}
    cand = load_json(RADAR_CANDIDATES, {}) or {}
    n = len(cand.get("candidates") or []) if isinstance(cand, dict) else 0
    return {
        "ok": True,
        "now": now_iso(),
        "candidates_count": n,
        "candidates_updated_at": cand.get("updated_at") if isinstance(cand, dict) else None,
        "merged_from_projects_at": cand.get("merged_from_projects_at") if isinstance(cand, dict) else None,
        "tg_fast_at": st.get("at"),
        "tg_fast_added": st.get("added") or [],
        "tg_fast_new_ids": st.get("new_message_ids") or [],
        "candidates_sha256": st.get("candidates_sha256"),
        "api_public_url": (PUBLIC_URL_PATH.read_text().strip() if PUBLIC_URL_PATH.exists() else None),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("WORKBENCH_API_PORT", "8780")),
                log_level="info", proxy_headers=True, forwarded_allow_ips="127.0.0.1",
                ws="websockets", ws_ping_interval=20.0, ws_ping_timeout=20.0)
