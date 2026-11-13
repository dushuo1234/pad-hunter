#!/usr/bin/env python3
"""Pad Hunter sniper — 6551 Twitter WSS last layer (dry_run via sniper_buy.fire_buy).

HOW TO START
  # prefer venv (has websockets):
  /workspace/project-monitor/.venv/bin/python sniper_6551.py watch
  # or:
  python3 sniper_6551.py watch          # will try import websockets; falls back to inject-only note

  # list imminent handles sourced for watch:
  python3 sniper_6551.py handles

  # try REST watch_add + WSS connect once (status only; never prints token):
  python3 sniper_6551.py probe

  # smoke without live WSS — same code path as a real CA push:
  python3 sniper_6551.py smoke
  python3 sniper_6551.py inject --handle RebateLaunch --ca 0x3333... --chain bsc

HANDLES
  Intersection of workbench_active.json pins and alerts/workbench_soon.jsonl
  「即将开盘」signals (start_at within -12h..+72h, or recent near_launch / 即将 x_post).

RECONNECT
  watch loop: connect → twitter.subscribe → ping/pong keepalive → on drop sleep
  backoff 1,2,4,…,30s and retry forever. Dedupes push id + fire_buy project|ca.

TOKEN
  secrets/6551_token  or env SNIPER_6551_TOKEN / OPENNEWS_TOKEN / OPENTWITTER_API_KEY
  Never logged in full.

BLOCKERS SEEN ON THIS BOX
  REST twitter_watch → 403 paid plan; REST lookups → 402 quota; WSS → 401.
  So live CA pushes need Max/Pro watch plan + points. Inject/smoke still exercises buy path.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
from sniper_buy import fire_buy, load_config  # noqa: E402

SH = ZoneInfo("Asia/Shanghai")
TOKEN_CANDIDATES = [
    BASE / "secrets" / "6551_token",
    BASE / ".secrets" / "6551_token",
]
WB = BASE / "workbench_active.json"
SOON = BASE / "alerts" / "workbench_soon.jsonl"
STATE = BASE / "alerts" / "sniper_6551_state.json"
STATUS_LOG = BASE / "alerts" / "sniper_6551_status.jsonl"
WSS_URLS = [
    "wss://ai.6551.io/open/twitter_wss",
    "wss://api.opentwitter.com/open/twitter_wss",
]
REST_BASES = [
    "https://ai.6551.io/open/",
    "https://api.opentwitter.com/open/",
]
EVM_CA_RE = re.compile(r"\b(0x[a-fA-F0-9]{40})\b")
# rough solana mint (base58 32-44)
SOL_CA_RE = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")

_seen_push_ids: set[int | str] = set()


def _now() -> str:
    return datetime.now(SH).isoformat(timespec="milliseconds")


def load_token() -> str | None:
    for env in ("SNIPER_6551_TOKEN", "OPENNEWS_TOKEN", "OPENTWITTER_API_KEY", "X6551_TOKEN"):
        v = (os.environ.get(env) or "").strip()
        if v:
            return v
    for p in TOKEN_CANDIDATES:
        try:
            t = p.read_text(encoding="utf-8").strip()
            if t:
                return t
        except Exception:
            pass
    return None


def token_meta(tok: str | None) -> dict:
    if not tok:
        return {"present": False}
    return {"present": True, "len": len(tok), "prefix": tok[:4] + "…", "suffix": "…" + tok[-4:]}


def _append_status(row: dict) -> None:
    STATUS_LOG.parent.mkdir(parents=True, exist_ok=True)
    # never allow token fields
    row = {k: v for k, v in row.items() if "token" not in k.lower() or k == "token_meta"}
    with open(STATUS_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _load_wb() -> dict[str, dict]:
    try:
        d = json.loads(WB.read_text(encoding="utf-8"))
    except Exception:
        return {}
    items = d.get("items") if isinstance(d, dict) else d
    out: dict[str, dict] = {}
    if isinstance(items, list):
        for it in items:
            h = (it.get("handle") or "").strip().lstrip("@")
            if h:
                out[h.lower()] = it
    return out


def imminent_projects(*, horizon_h: float = 72.0, lookback_h: float = 12.0, near_days: int = 7) -> list[dict]:
    """Workbench pins that look 即将开盘 from workbench_soon.jsonl."""
    wb = _load_wb()
    now = datetime.now(SH)
    best: dict[str, dict] = {}
    if not SOON.exists():
        # fallback: all workbench pins (caller can still inject); mark source
        return [
            {
                "handle": it.get("handle"),
                "name": it.get("name"),
                "chain": it.get("chain"),
                "reason": "workbench_all_fallback",
                "start_at": None,
            }
            for it in wb.values()
        ]

    for line in SOON.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        h = (r.get("handle") or "").strip().lstrip("@")
        hl = h.lower()
        if not hl or hl not in wb:
            continue
        keep = False
        reason = None
        sa = r.get("start_at")
        if sa:
            try:
                dt = datetime.fromisoformat(sa)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=SH)
                if now - timedelta(hours=lookback_h) <= dt <= now + timedelta(hours=horizon_h):
                    keep = True
                    reason = "start_at_window"
            except Exception:
                pass
        summary = str(r.get("summary") or "")
        if r.get("kind") == "x_post" and (
            r.get("x_bucket") == "near_launch" or "即将" in summary or "coming soon" in summary.lower()
            or "launching soon" in summary.lower() or "goes live" in summary.lower()
        ):
            try:
                ts = datetime.fromisoformat(r["ts"]) if r.get("ts") else now
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=SH)
                if ts >= now - timedelta(days=near_days):
                    keep = True
                    reason = reason or "near_launch_signal"
            except Exception:
                keep = True
                reason = reason or "near_launch_signal"
        if not keep:
            continue
        it = wb[hl]
        row = {
            "handle": h,
            "name": r.get("name") or it.get("name"),
            "chain": it.get("chain") or r.get("chain"),
            "start_at": sa,
            "reason": reason,
            "summary": summary[:120],
            "kind": r.get("kind"),
        }
        prev = best.get(hl)
        if not prev or (sa and (not prev.get("start_at") or sa < str(prev.get("start_at")))):
            best[hl] = row
    return sorted(best.values(), key=lambda x: (x.get("start_at") or "9999", (x.get("handle") or "").lower()))


def _rest_post(base: str, ep: str, body: dict, tok: str, timeout: float = 15.0) -> tuple[int, dict]:
    import urllib.request
    import urllib.error

    req = urllib.request.Request(
        base + ep,
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8", "replace") or "{}")
        except Exception:
            payload = {"error": str(e)}
        return e.code, payload if isinstance(payload, dict) else {"error": str(payload)}
    except Exception as e:
        return 0, {"error": type(e).__name__ + ": " + str(e)[:200]}


def watch_add(tok: str, username: str, *, remark: str = "pad-hunter-sniper") -> dict:
    """Enable CA pushes for one handle. Tries both REST bases."""
    body = {
        "username": username.lstrip("@"),
        "groupName": "pad-hunter-imminent",
        "remark": remark[:80],
        "newCaBol": True,
        "newTweetBol": True,       # also get tweets; we filter on ca field
        "newTweetReplyBol": False,
        "newTweetQuoteBol": True,
        "newRetweetBol": False,
        "updateNameBol": False,
        "updateDescBol": False,
        "updateAvatarBol": False,
        "updateBannerBol": False,
        "tweetToppingBol": False,
        "newFlwBol": False,
        "newUnFlwBol": False,
        "tierCode": "l2",
    }
    last = {}
    for base in REST_BASES:
        code, data = _rest_post(base, "twitter_watch_add", body, tok)
        last = {"base": base, "http": code, "data": data}
        if code in (200, 201) and (data.get("success") is True or data.get("ok") is True or data.get("data")):
            return {"ok": True, **last}
        if code in (401, 403, 402):
            # plan/quota — no point trying other base with same token semantics differently, but try once
            continue
    return {"ok": False, **last}


def watch_list(tok: str) -> dict:
    last = {}
    for base in REST_BASES:
        code, data = _rest_post(base, "twitter_watch", {}, tok)
        last = {"base": base, "http": code, "data": data}
        if code == 200:
            return {"ok": True, **last}
    return {"ok": False, **last}


def extract_ca(params: dict) -> str | None:
    ca = (params.get("ca") or "").strip()
    if ca and (ca.startswith("0x") and len(ca) == 42 or (not ca.startswith("0x") and 32 <= len(ca) <= 44)):
        return ca
    content = params.get("content")
    text = ""
    if isinstance(content, dict):
        text = str(content.get("text") or "")
        # nested
        for k in ("quotedStatus", "retweetedStatus"):
            q = content.get(k) or {}
            if isinstance(q, dict):
                text += " " + str(q.get("text") or "")
    elif isinstance(content, str):
        text = content
    m = EVM_CA_RE.search(text or "")
    if m:
        return m.group(1)
    # only accept sol-looking if eventType hints CA
    et = str(params.get("eventType") or "").upper()
    if "CA" in et:
        for m in SOL_CA_RE.finditer(text or ""):
            s = m.group(1)
            if s.lower().startswith("0x"):
                continue
            # skip obvious urls/handles
            if s.startswith("http"):
                continue
            return s
    return None


def handle_6551_event(params: dict, *, handle_map: dict[str, dict] | None = None, force: bool = False) -> dict | None:
    """Map a twitter.event params object → fire_buy(source=6551). Returns result or None if ignored."""
    if not isinstance(params, dict):
        return None
    pid = params.get("id")
    if pid is not None and not force:
        if pid in _seen_push_ids:
            return None
        _seen_push_ids.add(pid)
        if len(_seen_push_ids) > 20000:
            # drop oldest-ish by rebuild
            for _ in range(5000):
                _seen_push_ids.pop()

    et = str(params.get("eventType") or "").upper()
    ca = extract_ca(params)
    # accept CA / CA_CREATE / any event with non-empty ca
    if not ca:
        return None
    if et and et not in ("CA", "CA_CREATE", "NEW_TWEET", "NEW_TWEET_QUOTE", "NEW_TWEET_REPLY", "NEW_RETWEET") and "CA" not in et:
        # still allow if ca field present
        pass

    tw = (params.get("twAccount") or "").strip().lstrip("@")
    hmap = handle_map or {p["handle"].lower(): p for p in imminent_projects() if p.get("handle")}
    # also allow full workbench
    if tw.lower() not in hmap:
        wb = _load_wb()
        if tw.lower() in wb:
            it = wb[tw.lower()]
            hmap[tw.lower()] = {
                "handle": tw,
                "name": it.get("name"),
                "chain": it.get("chain"),
            }
        elif not force:
            # not a watched project — ignore
            return None

    meta = hmap.get(tw.lower()) or {"handle": tw, "name": params.get("twUserName"), "chain": None}
    chain = meta.get("chain") or "bsc"
    # fire FIRST (dedupe inside fire_buy), logging happens inside fire_buy after simulate
    result = fire_buy(
        ca=ca,
        chain=str(chain),
        project=meta.get("name") or tw,
        handle=meta.get("handle") or tw,
        source="6551",
        extra={
            "eventType": params.get("eventType"),
            "push_id": pid,
            "remark": params.get("remark"),
            "createdAt": params.get("createdAt"),
            "layer": "6551_wss",
        },
    )
    return result


def inject_event(*, handle: str, ca: str, chain: str | None = None, project: str | None = None,
                 event_type: str = "CA") -> dict:
    """Stub a 6551 CA push through the same handle_6551_event path."""
    wb = _load_wb()
    it = wb.get(handle.lstrip("@").lower()) or {}
    params = {
        "id": int(time.time() * 1000) % 10_000_000_000,
        "twAccount": handle.lstrip("@"),
        "twUserName": project or it.get("name") or handle,
        "eventType": event_type,
        "content": {"id": "0", "text": f"CA {ca}"},
        "ca": ca,
        "remark": "pad-hunter-inject",
        "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }
    hmap = {
        handle.lstrip("@").lower(): {
            "handle": handle.lstrip("@"),
            "name": project or it.get("name") or handle,
            "chain": chain or it.get("chain") or "bsc",
        }
    }
    r = handle_6551_event(params, handle_map=hmap, force=True)
    return r or {"ok": False, "error": "ignored"}


async def _wss_session(url: str, tok: str, handle_map: dict[str, dict]) -> str:
    """One connection lifecycle. Returns stop reason."""
    try:
        import websockets
    except ImportError:
        return "no_websockets"

    # try query token + bearer header
    full = f"{url}?token={tok}"
    try:
        async with websockets.connect(
            full,
            open_timeout=12,
            close_timeout=5,
            ping_interval=20,
            additional_headers={"Authorization": f"Bearer {tok}"},
        ) as ws:
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "twitter.subscribe"}))
            _append_status({"ts": _now(), "event": "wss_connected", "url": url, "token_meta": token_meta(tok)})
            # keepalive ping task
            async def pinger():
                while True:
                    await asyncio.sleep(25)
                    try:
                        await ws.send("ping")
                    except Exception:
                        return

            ping_task = asyncio.create_task(pinger())
            try:
                async for raw in ws:
                    if raw == "pong":
                        _append_status({"ts": _now(), "event": "wss_pong", "url": url})
                        continue
                    try:
                        msg = json.loads(raw)
                    except Exception:
                        continue
                    if msg.get("method") == "twitter.event":
                        params = msg.get("params") or {}
                        # speed: fire immediately
                        handle_6551_event(params, handle_map=handle_map)
                    elif msg.get("result"):
                        _append_status({"ts": _now(), "event": "wss_subscribe_ok", "url": url, "result": msg.get("result")})
                    elif msg.get("error"):
                        err = msg.get("error")
                        _append_status({"ts": _now(), "event": "wss_rpc_error", "url": url, "error": err})
            finally:
                ping_task.cancel()
            return "closed"
    except Exception as e:
        em = type(e).__name__ + ": " + str(e).replace(tok, "***")[:240]
        _append_status({"ts": _now(), "event": "wss_fail", "url": url, "error": em})
        return em


async def watch_loop(*, sync_watches: bool = True) -> None:
    tok = load_token()
    cfg = load_config()
    print(json.dumps({
        "msg": "sniper_6551 starting",
        "dry_run": cfg.get("dry_run"),
        "token": token_meta(tok),
        "wss": WSS_URLS,
    }, ensure_ascii=False), flush=True)
    if not tok:
        print("NO_TOKEN — running inject-only; use: python3 sniper_6551.py inject ...", flush=True)
        while True:
            await asyncio.sleep(3600)

    projects = imminent_projects()
    handle_map = {p["handle"].lower(): p for p in projects if p.get("handle")}
    print(json.dumps({"imminent_count": len(handle_map), "handles": sorted(handle_map.keys())[:40]}, ensure_ascii=False), flush=True)

    plan_block = None
    if sync_watches and handle_map:
        # attempt add for each (may 403)
        ok_n = fail_n = 0
        for hl, p in list(handle_map.items())[:50]:
            res = watch_add(tok, p["handle"], remark=f"imminent:{p.get('name') or ''}"[:80])
            if res.get("ok"):
                ok_n += 1
            else:
                fail_n += 1
                plan_block = {"http": res.get("http"), "error": (res.get("data") or {}).get("error") or res.get("data")}
                # if plan blocked, stop spamming adds
                if res.get("http") in (401, 402, 403):
                    break
        _append_status({"ts": _now(), "event": "watch_sync", "ok": ok_n, "fail": fail_n, "plan_block": plan_block})
        print(json.dumps({"watch_sync_ok": ok_n, "watch_sync_fail": fail_n, "plan_block": plan_block}, ensure_ascii=False), flush=True)

    backoff = 1
    url_i = 0
    while True:
        # refresh handle map periodically cheaply
        projects = imminent_projects()
        handle_map = {p["handle"].lower(): p for p in projects if p.get("handle")}
        url = WSS_URLS[url_i % len(WSS_URLS)]
        url_i += 1
        reason = await _wss_session(url, tok, handle_map)
        print(json.dumps({"wss_end": reason[:200], "backoff_s": backoff, "next_url": WSS_URLS[url_i % len(WSS_URLS)]}, ensure_ascii=False), flush=True)
        await asyncio.sleep(backoff)
        backoff = min(30, backoff * 2)


def cmd_probe() -> int:
    tok = load_token()
    print(json.dumps({"token": token_meta(tok), "dry_run": load_config().get("dry_run")}, ensure_ascii=False))
    if not tok:
        print(json.dumps({"rest": None, "wss": "no_token"}))
        return 2
    wl = watch_list(tok)
    # redact
    data = wl.get("data")
    print(json.dumps({"watch_list_http": wl.get("http"), "watch_list_ok": wl.get("ok"),
                      "watch_list_error": (data or {}).get("error") if isinstance(data, dict) else None}, ensure_ascii=False))
    # one watch_add attempt on a dummy? better use first imminent
    im = imminent_projects()
    if im:
        r = watch_add(tok, im[0]["handle"])
        print(json.dumps({"watch_add_http": r.get("http"), "watch_add_ok": r.get("ok"),
                          "watch_add_error": (r.get("data") or {}).get("error") if isinstance(r.get("data"), dict) else r.get("data"),
                          "handle": im[0]["handle"]}, ensure_ascii=False))

    async def wss_try():
        results = []
        try:
            import websockets  # noqa: F401
        except ImportError:
            return [{"error": "no_websockets_install_venv"}]
        for url in WSS_URLS:
            try:
                full = f"{url}?token={tok}"
                async with __import__("websockets").connect(
                    full, open_timeout=8, close_timeout=3,
                    additional_headers={"Authorization": f"Bearer {tok}"},
                ) as ws:
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1, "method": "twitter.subscribe"}))
                    await ws.send("ping")
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=4)
                        results.append({"url": url, "ok": True, "first": str(raw).replace(tok, "***")[:180]})
                    except asyncio.TimeoutError:
                        results.append({"url": url, "ok": True, "first": "silent_ok"})
            except Exception as e:
                results.append({"url": url, "ok": False, "error": type(e).__name__ + ": " + str(e).replace(tok, "***")[:180]})
        return results

    print(json.dumps({"wss": asyncio.run(wss_try())}, ensure_ascii=False))
    return 0


def cmd_smoke() -> int:
    """high_conf then 6551 same CA → buy + skip; 6551 new CA → buy. Uses inject path."""
    tag = f"s6551_{int(time.time())}"
    ca1 = "0x3333333333333333333333333333333333333333"
    ca2 = "0x4444444444444444444444444444444444444444"
    # layer1
    r1 = fire_buy(ca=ca1, chain="bsc", project="Smoke6551", handle=tag, source="high_conf")
    # layer2 same
    r2 = inject_event(handle=tag, ca=ca1, chain="bsc", project="Smoke6551")
    # layer2 new
    r3 = inject_event(handle=tag, ca=ca2, chain="bsc", project="Smoke6551")
    out = {
        "r1_high_conf": {k: r1.get(k) for k in ("action", "ms", "source", "would_buy")},
        "r2_6551_dup": {k: r2.get(k) for k in ("action", "ms", "source", "skipped_reason", "would_buy")},
        "r3_6551_new": {k: r3.get(k) for k in ("action", "ms", "source", "would_buy", "baw_cmdline")},
        "dry_run": load_config().get("dry_run"),
        "wss": "stub_inject_only_unless_plan",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ok = (r1.get("action") == "would_buy" and r2.get("action") == "skipped"
          and r2.get("skipped_reason") == "duplicate_project_ca" and r3.get("action") == "would_buy"
          and r3.get("source") == "6551")
    return 0 if ok else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="6551 WSS last-layer sniper (dry_run)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("handles", help="Print imminent workbench handles")
    sub.add_parser("probe", help="Token/REST/WSS status (redacted)")
    w = sub.add_parser("watch", help="Sync watches + WSS loop (reconnect)")
    w.add_argument("--no-sync", action="store_true", help="Skip twitter_watch_add")
    inj = sub.add_parser("inject", help="Stub one 6551 CA event into fire_buy")
    inj.add_argument("--handle", required=True)
    inj.add_argument("--ca", required=True)
    inj.add_argument("--chain", default=None)
    inj.add_argument("--project", default=None)
    sub.add_parser("smoke", help="high_conf + 6551 dup/new smoke")
    args = p.parse_args(argv)

    if args.cmd == "handles":
        rows = imminent_projects()
        print(json.dumps({"count": len(rows), "items": rows}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "probe":
        return cmd_probe()
    if args.cmd == "watch":
        asyncio.run(watch_loop(sync_watches=not args.no_sync))
        return 0
    if args.cmd == "inject":
        r = inject_event(handle=args.handle, ca=args.ca, chain=args.chain, project=args.project)
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return 0 if r.get("ok") or r.get("action") == "skipped" else 1
    if args.cmd == "smoke":
        return cmd_smoke()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
