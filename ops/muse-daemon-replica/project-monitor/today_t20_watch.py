#!/usr/bin/env python3
"""今日项目清单 · 开盘前 20 分钟（T-20）高频 CA 监测。

窗口：listing_at ∈ (listing−T20_MIN, listing+T20_AFTER]；过点后仍在今日清单且未固定CA 则继续盯（不致盲）
  - listing_at 每轮从 listing_times.json sticky 覆盖 today_projects（不靠慢 sync）
  - 6551：优先 WSS（watch_add + twitter.subscribe）；失败则 REST 轮询官推（约 5s）
  - 既有 CA 策略：提频读 ca_finds；写 today_projects_boost.json 让 soon_watch 官网≈5s
  - 固定 CA → 立即 per-handle wake（不与兄弟项目拼成一条才叫醒）+ workbench/jsonl + dry_run fire_buy
  - 多项目同一天并行：WSS handle_map 同时盯多个 T-20 号，互不顶替；新进窗口立刻 watch_add
  - 固定 CA（官推 或 部署者/关联钱包）确认后：推送一次 → force_launch/已开盘 → 该号 stopped 停推停盯，其它号继续

状态：alerts/today_t20_state.json
绝不编造 listing_at / CA；NFT≠token；炼油：代币> NFT；「固定CA」=官推或部署者/关联钱包；其它高置信仅待确认；官推固定才已开盘；时区 Asia/Shanghai。
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import signal
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
sys.path.insert(0, str(BASE))

SH = ZoneInfo("Asia/Shanghai")
TODAY = BASE / "today_projects.json"
BOOST = BASE / "today_projects_boost.json"
CA_FINDS = BASE / "ca_finds.json"
STATE = BASE / "alerts" / "today_t20_state.json"
ALERTS = BASE / "alerts" / "today_t20_alerts.jsonl"
SOON = BASE / "alerts" / "workbench_soon.jsonl"
MSG = BASE / "_today_t20_highconf_msg.txt"
MSG_HISTORY = BASE / "_today_t20_highconf_history.txt"
LAUNCH_MSG = BASE / "_today_t20_launched_msg.txt"
LAUNCH_HISTORY = BASE / "_today_t20_launched_history.txt"
LATEST_FIXED = BASE / "_today_t20_latest_fixed.txt"
WAKE_DIR = BASE / "alerts" / "today_t20_wake"
WAKE_QUEUE = BASE / "alerts" / "today_t20_wake_queue.jsonl"
LISTING_TIMES = BASE / "listing_times.json"
LISTING_STICKY = BASE / "_baseline_listing_times_sticky.json"
TOKEN_FILE = BASE / "workbench_api_token.txt"
API = os.environ.get("PAD_HUNTER_CF_API", "https://api.adualpha.win").rstrip("/")
UA = "PadHunterTodayT20/1.0"

T20_MIN = float(os.environ.get("TODAY_T20_MINUTES", "60"))
T20_AFTER_MIN = float(os.environ.get("TODAY_T20_AFTER_MINUTES", "60"))  # post-listing grace
T20_KEEP_AFTER_H = float(os.environ.get("TODAY_T20_KEEP_AFTER_H", "6"))  # still on today list
T5_MIN = float(os.environ.get("TODAY_T5_MINUTES", "5"))  # 开盘前5分钟：推特 WSS 实时推 CA
T5_SITE_EVERY = float(os.environ.get("TODAY_T5_SITE_EVERY", "2"))
TICK = float(os.environ.get("TODAY_T20_TICK", "2"))
REST_EVERY = float(os.environ.get("TODAY_T20_REST_EVERY", "5"))
CA_POLL_EVERY = float(os.environ.get("TODAY_T20_CA_EVERY", "1"))
T20_SITE_EVERY = float(os.environ.get("TODAY_T20_SITE_EVERY", "3"))
BOOST_SITE_EVERY = 15.0

EVM_CA_RE = re.compile(r"\b(0x[a-fA-F0-9]{40})\b")
SOL_CA_RE = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")
# skip common base58 false positives
SOL_FALSE = re.compile(r"^(https?|status|twitter|http)", re.I)

RUNNING = True
MIRRORS = [
    Path("/workspace/push-radar/data/today_projects.json"),
    Path("/workspace/publish-pages-data/today_projects.json"),
]


def now() -> datetime:
    return datetime.now(SH)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone(SH).isoformat(timespec="seconds")


def norm(h: str | None) -> str:
    return (h or "").strip().lstrip("@").lower()


def parse_dt(val) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SH)
        return dt.astimezone(SH)
    except Exception:
        return None


def load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def dump_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_state() -> dict:
    st = load_json(STATE, {})
    if not isinstance(st, dict):
        st = {}
    st.setdefault("handles", {})
    st.setdefault("dedupe", {})
    st.setdefault("mode", "init")
    st.setdefault("wss_ok", None)
    return st


def save_state(st: dict) -> None:
    st["updated_at"] = iso()
    dump_json(STATE, st)


def wb_token() -> str:
    t = os.environ.get("PAD_HUNTER_WORKBENCH_TOKEN_NEW", "").strip()
    if not t and TOKEN_FILE.exists():
        t = TOKEN_FILE.read_text().strip()
    return t


def api_post(path: str, body: dict):
    import urllib.request
    import urllib.error

    data = json.dumps(body).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        method="POST",
        headers={
            "X-Pad-Hunter-Token": wb_token(),
            "Content-Type": "application/json",
            "User-Agent": UA,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw[:200]
    except urllib.error.HTTPError as e:
        return e.code, {"error": str(e)[:160]}
    except Exception as e:
        return 0, {"error": type(e).__name__ + ": " + str(e)[:160]}


_listing_cache: dict = {"at": 0.0, "map": {}}


def load_live_listing_map(*, force: bool = False) -> dict[str, str]:
    """Fresh listing_at by handle from listing_times (+ sticky). Re-read often so T-20
    does not wait on slow today_projects sync.
    """
    global _listing_cache
    now_m = time.time()
    if not force and _listing_cache["map"] and (now_m - float(_listing_cache["at"])) < 5.0:
        return _listing_cache["map"]
    out: dict[str, str] = {}
    sticky = load_json(LISTING_STICKY, {})
    if isinstance(sticky, dict):
        for k, v in sticky.items():
            if isinstance(v, str) and v.strip():
                out[norm(k)] = v.strip()
            elif isinstance(v, dict) and v.get("listing_at"):
                out[norm(k)] = str(v.get("listing_at")).strip()
    doc = load_json(LISTING_TIMES, {})
    if isinstance(doc, dict):
        for it in (doc.get("items") or []) + (doc.get("within_next_3_days") or []):
            if not isinstance(it, dict):
                continue
            h = norm(it.get("handle"))
            la = it.get("listing_at")
            if h and la:
                out[h] = str(la).strip()
    _listing_cache = {"at": now_m, "map": out}
    return out


def apply_live_listing(it: dict) -> dict:
    """Overlay sticky/listing_times onto a today_projects row (shallow copy if changed)."""
    h = norm(it.get("handle"))
    live = load_live_listing_map().get(h)
    if not live:
        return it
    cur = str(it.get("listing_at") or "").strip()
    if live == cur:
        return it
    out = dict(it)
    out["listing_at"] = live
    out["listing_at_display"] = live
    out["_listing_live_from"] = "listing_times"
    return out


def today_items() -> list[dict]:
    doc = load_json(TODAY, {})
    items = doc.get("items") if isinstance(doc, dict) else []
    load_live_listing_map(force=False)
    return [
        apply_live_listing(it)
        for it in (items or [])
        if isinstance(it, dict) and it.get("handle")
    ]


def item_launched_or_done(it: dict, st: dict | None = None) -> bool:
    """True when this handle should leave T-20 (fixed / launched / stopped)."""
    hl = norm(it.get("handle"))
    if st is None:
        try:
            st = load_state()
        except Exception:
            st = {}
    hst = (st.get("handles") or {}).get(hl) or {}
    if hst.get("stopped"):
        return True
    status = str(it.get("status") or it.get("listing") or "")
    if "已开盘" in status or "已上线" in status:
        return True
    low = status.lower()
    if low in ("launched", "listed"):
        return True
    if it.get("launched") or it.get("fixed_ca") or it.get("ca_fixed"):
        return True
    return False


def in_t20(it: dict, ref: datetime | None = None, st: dict | None = None) -> bool:
    """T-20 with post-listing grace. Past listing must not go blind while still on today list.

    Window: (listing_at - T20_MIN, listing_at + T20_AFTER_MIN]
    OR listing passed but within KEEP_AFTER hours and not yet fixed/stopped.
    """
    ref = ref or now()
    if item_launched_or_done(it, st):
        return False
    dt = parse_dt(it.get("listing_at"))
    if not dt:
        return False
    start = dt - timedelta(minutes=T20_MIN)
    end = dt + timedelta(minutes=T20_AFTER_MIN)
    keep_end = dt + timedelta(hours=T20_KEEP_AFTER_H)
    if start < ref <= end:
        return True
    if dt < ref <= keep_end:
        return True
    return False


def t20_active(ref: datetime | None = None, st: dict | None = None) -> list[dict]:
    ref = ref or now()
    load_live_listing_map(force=True)
    if st is None:
        try:
            st = load_state()
        except Exception:
            st = {}
    out = []
    for it in today_items():
        if in_t20(it, ref, st=st):
            out.append(it)
    return out


def in_t5(it: dict, ref: datetime | None = None, st: dict | None = None) -> bool:
    """开盘前 5 分钟 + 短过点宽限：6551 推特 WSS 实时推 CA。"""
    ref = ref or now()
    if item_launched_or_done(it, st):
        return False
    dt = parse_dt(it.get("listing_at"))
    if not dt:
        return False
    post = min(T20_AFTER_MIN, 15.0)
    return (dt - timedelta(minutes=T5_MIN)) < ref <= (dt + timedelta(minutes=post))


def t5_active(ref: datetime | None = None, st: dict | None = None) -> list[dict]:
    ref = ref or now()
    load_live_listing_map(force=False)
    if st is None:
        try:
            st = load_state()
        except Exception:
            st = {}
    out = []
    for it in today_items():
        if in_t5(it, ref, st=st):
            out.append(it)
    return out


def write_fixed_ca_wake(
    *,
    it: dict,
    ca: str,
    chain: str | None,
    source: str,
    conf: str,
    kind: str = "fixed",
    extra_lines: list[str] | None = None,
) -> None:
    """Immediate per-CA wake — NEVER batch sibling projects into one handoff.

    Writes per-handle wake + latest_fixed (overwrite) + MSG (this CA only) + queue jsonl.
    Sibling batching in WeChat/chat is automation-side if it still merges.
    """
    handle = (it.get("handle") or "").lstrip("@")
    hl = norm(handle)
    body_lines = [
        f"🎯 T-20 {kind} · {conf} · {it.get('name')}（@{handle}）",
        f"- CA：`{ca}`" + (f"（{chain}）" if chain else ""),
        f"- 开盘：{it.get('listing_at_display') or it.get('listing_at')}（Asia/Shanghai）",
        f"- 来源：{source}",
        f"- sniper：dry_run（不实买）",
        f"- 官网：{it.get('site') or '—'}",
        f"- wake_at：{iso()}",
        f"- handle：{handle}",
    ]
    if extra_lines:
        body_lines.extend(extra_lines)
    body = "\n".join(body_lines) + "\n"

    WAKE_DIR.mkdir(parents=True, exist_ok=True)
    wake_path = WAKE_DIR / f"{hl or 'unknown'}.txt"
    wake_path.write_text(body, encoding="utf-8")
    LATEST_FIXED.write_text(body, encoding="utf-8")
    MSG.write_text(body, encoding="utf-8")
    try:
        hist = MSG_HISTORY.read_text(encoding="utf-8") if MSG_HISTORY.exists() else ""
    except Exception:
        hist = ""
    MSG_HISTORY.write_text((hist + ("\n\n" if hist.strip() else "") + body), encoding="utf-8")

    rec = {
        "ts": iso(),
        "handle": handle,
        "name": it.get("name"),
        "ca": ca,
        "chain": chain,
        "source": source,
        "confidence": conf,
        "kind": kind,
        "listing_at": it.get("listing_at"),
        "wake_file": str(wake_path),
    }
    WAKE_QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with WAKE_QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{iso()}] WAKE fixed_ca @{handle} ca={ca} file={wake_path.name}", flush=True)


def write_boost(active: list[dict], all_handles: list[str] | None = None) -> None:
    """Refresh boost: today @10s; T-60 @3s; T-5 @2s (推特 WSS 实时 CA)."""
    if all_handles is None:
        all_handles = [it["handle"] for it in today_items()]
    t20_h = [it["handle"] for it in active]
    t5_h = [it["handle"] for it in t5_active()]
    handle_site_every = {norm(h): T20_SITE_EVERY for h in t20_h}
    for h in t5_h:
        handle_site_every[norm(h)] = T5_SITE_EVERY
    doc = {
        "handles": all_handles,
        "generated_at": iso(),
        "site_every_seconds": BOOST_SITE_EVERY,
        "t20_handles": t20_h,
        "t5_handles": t5_h,
        "t20_site_every_seconds": T20_SITE_EVERY,
        "t5_site_every_seconds": T5_SITE_EVERY,
        "t20_window_minutes": T20_MIN,
        "t5_window_minutes": T5_MIN,
        "handle_site_every": handle_site_every,
        "note": "T-5: 6551 WSS realtime CA; site≈2s. T-60 site≈3s; today list≈10s",
    }
    dump_json(BOOST, doc)


def extract_cas_from_text(text: str) -> list[tuple[str, str]]:
    """Return list of (ca, chain_guess). Prefer EVM; Sol only when looks like mint."""
    out: list[tuple[str, str]] = []
    seen = set()
    for m in EVM_CA_RE.finditer(text or ""):
        ca = m.group(1)
        k = ca.lower()
        if k not in seen:
            seen.add(k)
            out.append((ca, "evm"))
    # Solana: only if text hints CA/contract/token and not URL-ish
    hint = bool(re.search(r"\b(CA|contract|token|mint|\$[A-Z]{2,10}|合约|代币)\b", text or "", re.I))
    if hint:
        for m in SOL_CA_RE.finditer(text or ""):
            s = m.group(1)
            if s.lower().startswith("0x") or SOL_FALSE.match(s) or len(s) < 32:
                continue
            if s not in seen:
                seen.add(s)
                out.append((s, "solana"))
    return out



def classify_ca(addr: str, chain_hint: str | None = None) -> dict:
    """Return ca_gate verify dict; never invent. Fail-soft → unknown."""
    try:
        from ca_gate import verify_address

        return verify_address(addr, chain_hint=chain_hint) or {}
    except Exception as e:
        return {"address": addr, "kind": "unknown", "is_token": False, "error": str(e)[:120]}


def rank_cas(cas: list[tuple[str, str]], chain_hint: str | None = None) -> list[dict]:
    """炼油规则：代币 CA 优先于 NFT；hybrid/未知垫底。返回 [{ca,chain,kind,is_token,verify}, ...]"""
    ranked = []
    for ca, ch in cas:
        v = classify_ca(ca, chain_hint or ch)
        kind = str(v.get("kind") or "unknown").lower()
        is_tok = bool(v.get("is_token")) or kind == "token"
        # score: token=100, unknown-with-erc20-ish=40, hybrid=10, nft=0, wallet/invalid=-1
        if is_tok or kind == "token":
            score = 100
        elif kind in ("nft",):
            score = 0
        elif kind in ("hybrid_404", "hybrid"):
            score = 10
        elif kind in ("wallet", "invalid"):
            score = -1
        else:
            score = 40
        ranked.append({
            "ca": ca,
            "chain": chain_hint or ch,
            "kind": kind,
            "is_token": is_tok,
            "score": score,
            "verify": {k: v.get(k) for k in ("kind", "is_token", "label_zh", "note_zh", "decimals", "symbol", "name") if k in v},
        })
    ranked.sort(key=lambda r: (-r["score"], r["ca"].lower()))
    return ranked


def prefer_token_cas(cas: list[tuple[str, str]], chain_hint: str | None = None) -> list[dict]:
    """Keep token CAs first; drop pure NFT from high-conf/launch path (still return them tagged)."""
    return rank_cas(cas, chain_hint=chain_hint)


def tweet_text(tw: dict) -> str:
    if not isinstance(tw, dict):
        return ""
    parts = [
        str(tw.get("text") or tw.get("fullText") or tw.get("full_text") or ""),
        str(tw.get("content") or ""),
    ]
    for k in ("quotedStatus", "retweetedStatus", "quoted_status", "retweeted_status"):
        q = tw.get(k)
        if isinstance(q, dict):
            parts.append(str(q.get("text") or q.get("fullText") or q.get("full_text") or ""))
    return " ".join(parts)


def own_tweet_text(tw: dict) -> str:
    """Author's own text only (no quoted / retweeted body). Retweets → ''."""
    if not isinstance(tw, dict):
        return ""
    if isinstance(tw.get("retweetedStatus") or tw.get("retweeted_status"), dict):
        return ""
    t = " ".join([
        str(tw.get("text") or tw.get("fullText") or tw.get("full_text") or ""),
        str(tw.get("content") or ""),
    ])
    if t.lstrip().startswith("RT @"):
        return ""
    return t


def is_high_conf_find(f: dict) -> bool:
    try:
        from sniper_buy import is_high_conf_find as _h

        return bool(_h(f))
    except Exception:
        conf = str(f.get("confidence") or "").lower()
        if f.get("ca_status") == "confirmed" and f.get("alert_ok") and f.get("is_token"):
            return True
        kind = str(f.get("kind") or "").lower()
        if kind in ("nft", "hybrid_404", "hybrid", "wallet"):
            return False
        if conf in ("high", "confirmed", "medium") and f.get("is_token") and kind != "wallet":
            if f.get("ca_status") in ("not_ca", "suspected_copycat", "superseded"):
                return False
            return conf != "medium" or bool(f.get("alert_ok") or f.get("official_x_confirmed"))
        return False


def is_official_x_ca(f: dict) -> bool:
    if f.get("official_x_confirmed"):
        return True
    if f.get("provenance") in ("official_x", "both"):
        return True
    if f.get("ca_status") == "confirmed" and f.get("alert_ok") and f.get("is_token"):
        # confirmed token with X source lineage
        src = str(f.get("source") or "").lower()
        origins = " ".join(
            str((s or {}).get("origin") or "") for s in (f.get("sources") or []) if isinstance(s, dict)
        ).lower()
        if "x_ca" in src or "x_ca" in origins or "official_x" in origins or "x_post" in origins:
            return True
    return False


def is_fixed_ca_find(f: dict, *, official_tweet: bool = False) -> tuple[bool, str]:
    """炼油固定CA：官推 或 部署者/关联钱包。纯高置信仍待确认。"""
    try:
        from ca_confidence import is_ca_fixed

        return is_ca_fixed(f, official_x=True if official_tweet else None)
    except Exception:
        if official_tweet or is_official_x_ca(f):
            return True, "official_x"
        return False, "candidate_not_fixed"


def finds_for_handle(handle: str) -> list[dict]:
    doc = load_json(CA_FINDS, {})
    finds = doc.get("finds") if isinstance(doc, dict) else []
    hl = norm(handle)
    out = []
    for f in finds or []:
        if not isinstance(f, dict):
            continue
        if norm(f.get("handle")) == hl:
            out.append(f)
    # 炼油：代币 CA 排前；NFT/非 token 靠后
    def _score(f: dict) -> tuple:
        kind = str(f.get("kind") or "").lower()
        is_tok = bool(f.get("is_token")) or kind == "token"
        off = 1 if is_official_x_ca(f) else 0
        hi = 1 if is_high_conf_find(f) else 0
        tok = 2 if is_tok else (0 if kind == "nft" else 1)
        return (-tok, -off, -hi)
    out.sort(key=_score)
    return out


def format_highconf_msg(it: dict, ca: str, chain: str | None, source: str, conf: str) -> str:
    return "\n".join(
        [
            f"🎯 T-20 高置信CA · {conf} · {it.get('name')}（@{it.get('handle')}）",
            f"- CA：`{ca}`" + (f"（{chain}）" if chain else ""),
            f"- 开盘：{it.get('listing_at_display') or it.get('listing_at')}（Asia/Shanghai）",
            f"- 来源：{source}",
            f"- sniper：dry_run（不实买）",
            f"- 官网：{it.get('site') or '—'}",
        ]
    )


def format_launched_msg(it: dict, ca: str, chain: str | None, source: str) -> str:
    return "\n".join(
        [
            f"✅ 官推CA确认 · 已开盘 · {it.get('name')}（@{it.get('handle')}）",
            f"- CA：`{ca}`" + (f"（{chain}）" if chain else ""),
            f"- 原定开盘：{it.get('listing_at_display') or it.get('listing_at')}（Asia/Shanghai）",
            f"- 来源：{source}",
            f"- 已移出今日项目清单并停止 T-20 监测",
        ]
    )


def append_alert(rec: dict) -> None:
    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    with ALERTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    try:
        with SOON.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def push_workbench(rec: dict) -> None:
    try:
        code, body = api_post(
            "/v1/workbench/alert",
            {"alerts": [rec], "client_id": "box-today-t20"},
        )
        rec["_push"] = {"code": code, "body": body if isinstance(body, dict) else str(body)[:120]}
    except Exception as e:
        rec["_push"] = {"error": str(e)[:160]}
    # realtime today CA API (chain noted on wallet)
    if rec.get("ca") or rec.get("address"):
        try:
            from today_ca_push import push_event, chain_note, norm_chain
            ch = norm_chain(rec.get("chain"))
            ca = (rec.get("ca") or rec.get("address") or "").strip()
            push_event(
                {
                    "id": rec.get("id") or "",
                    "handle": rec.get("handle"),
                    "name": rec.get("name"),
                    "ca": ca,
                    "chain": ch,
                    "chain_note": chain_note(ch, ca),
                    "wallet_note": chain_note(ch, ca),
                    "ts": rec.get("ts"),
                    "confidence": rec.get("confidence"),
                    "ca_fixed": rec.get("ca_fixed"),
                    "ca_fixed_reason": rec.get("ca_fixed_reason"),
                    "ca_status": rec.get("ca_status"),
                    "is_token": rec.get("is_token", True),
                    "kind": rec.get("kind") or "ca",
                    "source": rec.get("source") or "today_t20",
                    "evidence_url": rec.get("tweet_url"),
                    "client_id": "box-today-t20",
                }
            )
        except Exception as e:
            rec["_today_ca_push"] = {"error": str(e)[:160]}


def push_today_tg_ca(
    it: dict,
    ca: str,
    *,
    kind: str = "ca",
    summary: str | None = None,
    chain: str | None = None,
    official_x: bool = False,
) -> None:
    """bot123123 sync push — pure code path, NEVER waits on agent/MSG/wake."""
    try:
        from telegram_today_only import push_ca

        r = push_ca(
            handle=it.get("handle") or "",
            name=it.get("name"),
            ca=ca,
            chain=chain or it.get("chain"),
            kind=kind,
            summary=summary,
            listing_at=it.get("listing_at_display") or it.get("listing_at"),
            site=it.get("site"),
            official_x=True if official_x else None,
        )
        if r.get("skipped"):
            print(f"[tg] skip CA @{it.get('handle')}: {r.get('skipped')}", flush=True)
        elif r.get("ok"):
            print(f"[tg] CA pushed @{it.get('handle')} mid={r.get('message_id')}", flush=True)
        else:
            print(f"[tg] CA push fail @{it.get('handle')}: {r}", flush=True)
    except Exception as e:
        print(f"[tg] CA push error: {e}", flush=True)


def emit_alert(
    st: dict,
    *,
    it: dict,
    kind: str,
    summary: str,
    ca: str | None = None,
    chain: str | None = None,
    source: str | None = None,
    confidence: str | None = None,
    tweet_url: str | None = None,
    push: bool = True,
) -> bool:
    # stopped handle: no more pushes (allow the stop/launch notice through)
    _hl = norm(it.get("handle"))
    _hst = (st.get("handles") or {}).get(_hl) or {}
    if _hst.get("stopped") and kind not in ("today_t20", "launched") and "停止" not in (summary or ""):
        return False
    h = it.get("handle")
    dk = f"t20|{kind}|{norm(h)}|{(ca or '').lower()}|{source or ''}|{summary[:80]}"
    if dk in st.setdefault("dedupe", {}):
        return False
    st["dedupe"][dk] = iso()
    if len(st["dedupe"]) > 8000:
        # drop oldest half by keeping last 4000 insertion order (py3.7+)
        keys = list(st["dedupe"].keys())
        for k in keys[: len(keys) - 4000]:
            st["dedupe"].pop(k, None)
    rec = {
        "id": hashlib.sha1(dk.encode()).hexdigest()[:16],
        "ts": iso(),
        "handle": h,
        "name": it.get("name"),
        "kind": kind,  # today_t20 / ca / x_post
        "t20": True,
        "listing_at": it.get("listing_at"),
        "listing_at_display": it.get("listing_at_display"),
        "summary": summary,
        "address": ca,
        "ca": ca,
        "chain": chain or it.get("chain"),
        "source": source,
        "confidence": confidence,
        "tweet_url": tweet_url or it.get("tweet_url"),
        "site": it.get("site"),
        "client_tag": "today_t20",
    }
    # HARD: CA → Telegram is sync code path FIRST. No agent/MSG/wake relay.
    # TODAY_TG_BY_T20=1 required. Gates: today-list + fixed/official (inside push_ca).
    if push and os.environ.get("TODAY_TG_BY_T20") == "1" and ca and kind in ("ca", "today_t20", "x_post", "launched"):
        conf_l = (confidence or "").lower()
        src_l = (source or "").lower()
        summ = summary or ""
        is_fixed = (
            kind == "launched"
            or conf_l in ("confirmed",)
            or "固定CA" in summ
            or "已开盘" in summ
            or "官推" in summ
            or "official" in src_l
            or "official_x" in src_l
            or "deployer" in src_l
        )
        if is_fixed:
            tg_kind = "launched" if (kind == "launched" or "已开盘" in summ) else "ca"
            push_today_tg_ca(
                it,
                ca,
                kind=tg_kind,
                summary=summary,
                chain=chain,
                official_x=True,  # T-20 already classified fixed; do not wait on ca_finds
            )
        else:
            print(f"[tg] skip CA @{h}: need fixed/official (conf={confidence!r} src={source!r})", flush=True)
    append_alert(rec)
    if push:
        try:
            push_workbench(rec)
        except Exception as e:
            print(f"[workbench] push error (TG already attempted): {e}", flush=True)
    print(f"[{rec['ts']}] ALERT {kind} @{h} {summary[:120]}", flush=True)
    return True


def dry_fire(ca: str, chain: str | None, it: dict, source: str) -> dict:
    try:
        from sniper_buy import fire_buy

        return fire_buy(
            ca=ca,
            chain=str(chain or it.get("chain") or "bsc"),
            project=it.get("name") or it.get("handle"),
            handle=it.get("handle"),
            source=source,
            extra={"layer": "today_t20", "listing_at": it.get("listing_at")},
        )
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def drop_from_today(handle: str) -> bool:
    doc = load_json(TODAY, {})
    items = list(doc.get("items") or [])
    hl = norm(handle)
    new_items = [it for it in items if norm(it.get("handle")) != hl]
    if len(new_items) == len(items):
        return False
    doc["items"] = new_items
    doc["count"] = len(new_items)
    doc["generated_at"] = iso()
    doc["last_t20_drop"] = {"handle": handle, "at": iso()}
    dump_json(TODAY, doc)
    for dest in MIRRORS:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(TODAY, dest)
        except OSError:
            pass
    # keep boost in sync
    write_boost(t20_active(), [it["handle"] for it in new_items])
    return True


def mark_launched_official(it: dict, ca: str, chain: str | None, evidence: str, evidence_url: str | None) -> dict:
    """force_launch + mark prune + drop today."""
    out = {"force": False, "mark": None, "dropped": False}
    try:
        from mark_launched_from_ca import force_launch, mark

        out["force"] = bool(
            force_launch(
                handle=it.get("handle"),
                project=it.get("name"),
                ca=ca,
                ca_chain=chain or it.get("chain"),
                reason="today_t20_official_x_ca",
                evidence=evidence,
                evidence_url=evidence_url or it.get("tweet_url"),
            )
        )
        out["mark"] = mark()
    except Exception as e:
        out["error"] = str(e)[:240]
    out["dropped"] = drop_from_today(it.get("handle") or "")
    return out


def rest_poll_handle(handle: str, n: int = 5) -> tuple[list[dict], dict]:
    """6551 REST user_tweets. Returns (tweets, meta)."""
    meta = {"ok": False, "mode": "rest"}
    try:
        import x6551

        tweets = x6551.user_tweets(handle.lstrip("@"), n=n, replies=False)
        meta["ok"] = True
        meta["n"] = len(tweets)
        return tweets or [], meta
    except Exception as e:
        status = getattr(e, "status", None)
        meta["error"] = str(e)[:160]
        meta["status"] = status
        if status in (402, 403, 401):
            meta["quota_or_plan"] = True
        return [], meta


def process_tweets(st: dict, it: dict, tweets: list[dict], *, source_tag: str) -> None:
    hl = norm(it.get("handle"))
    hst = st["handles"].setdefault(hl, {})
    seen_ids = set(hst.get("seen_tweet_ids") or [])
    for tw in tweets:
        tid = str(tw.get("id") or tw.get("tweetId") or tw.get("rest_id") or "")
        text = tweet_text(tw)
        if not text.strip():
            continue
        if tid and tid in seen_ids:
            continue
        if tid:
            seen_ids.add(tid)
        cas = extract_cas_from_text(text)
        # 2026-10-29 Capta fix: only a PROJECT official account's OWN text can yield 固定CA.
        try:
            from ca_confidence import non_project_account
            _npa, _npa_why = non_project_account(it.get("handle"))
        except Exception:
            _npa, _npa_why = False, None
        _own = own_tweet_text(tw)
        _own_cas = {c.lower() for c, _ in (extract_cas_from_text(_own) if _own.strip() else [])}
        _acct_lbl = "X更新（个人号/KOL，非官推）" if _npa else "官推更新"
        if not cas:
            # still record x_post pulse for UI black box (deduped lightly)
            if tid:
                emit_alert(
                    st,
                    it=it,
                    kind="x_post",
                    summary=f"【{it.get('name')}】T-20 {_acct_lbl}：{(text[:100] + '…') if len(text) > 100 else text}",
                    source=source_tag,
                    tweet_url=f"https://x.com/{it.get('handle')}/status/{tid}" if tid else it.get("tweet_url"),
                    push=True,
                )
            continue
        # 炼油：同帖多 CA 时代币优先；纯 NFT 不进高置信/已开盘出口
        ranked = prefer_token_cas(
            cas,
            chain_hint=it.get("chain") if it.get("chain") and it.get("chain") not in ("未知",) else None,
        )
        for r in ranked:
            ca = r["ca"]
            chain = r["chain"]
            tweet_url = f"https://x.com/{it.get('handle')}/status/{tid}" if tid else it.get("tweet_url")
            if r["score"] <= 0 or r["kind"] == "nft":
                emit_alert(
                    st,
                    it=it,
                    kind="x_post",
                    summary=f"【{it.get('name')}】官推出现 NFT/非代币地址 `{ca}`（已降权，不作出币 CA）",
                    ca=ca,
                    chain=chain,
                    source=f"{source_tag}:official_tweet_nft_demoted",
                    confidence="low",
                    tweet_url=tweet_url,
                )
                continue
            # 2026-10-29 Capta gates — demote to candidate (no lock / wake / buy / 已开盘 / TG):
            try:
                from ca_confidence import denied_ca, token_matches_project
                _den = denied_ca(ca)
            except Exception:
                _den, token_matches_project = None, None
            _demote = None
            if _den:
                _demote = f"denied_ca:{_den.get('ca_status') or 'denied'}"
            elif _npa:
                _demote = f"kol_not_official:{_npa_why}"
            elif ca.lower() not in _own_cas:
                _demote = "ca_only_in_quote_or_retweet"
            elif token_matches_project is not None:
                _vf = r.get("verify") or {}
                _m = token_matches_project(
                    _vf.get("symbol"), _vf.get("name"),
                    project_name=it.get("name"), handle=it.get("handle"), text=text,
                    extra_tickers=[x for x in (it.get("ticker"), it.get("symbol")) if x],
                )
                if _m is False:
                    _demote = f"symbol_mismatch:{_vf.get('symbol')}/{_vf.get('name')}"
            if _demote:
                emit_alert(
                    st,
                    it=it,
                    kind="x_post",
                    summary=(f"【{it.get('name')}】X 提及 CA `{ca}`（候选，不算固定CA：{_demote[:80]}）"),
                    ca=ca,
                    chain=chain,
                    source=f"{source_tag}:candidate_{_demote.split(':')[0]}",
                    confidence="low",
                    tweet_url=tweet_url,
                    push=False,
                )
                print(f"[gate] demote @{it.get('handle')} ca={ca} reason={_demote}", flush=True)
                continue
            # Official handle tweet with token CA → 固定CA（条件②）+ launch
            conf = "confirmed"
            msg = format_highconf_msg(it, ca, chain, f"{source_tag}:official_tweet", conf)
            emit_alert(
                st,
                it=it,
                kind="ca",
                summary=f"【{it.get('name')}】T-20 固定CA · 官推代币 `{ca}`",
                ca=ca,
                chain=chain,
                source=f"{source_tag}:official_tweet",
                confidence=conf,
                tweet_url=tweet_url,
            )
            try:
                from ca_confidence import record_lock
                record_lock(
                    handle=it.get("handle"),
                    name=it.get("name"),
                    address=ca,
                    ca_role="token",
                    post_url=tweet_url,
                    note=f"today_t20:{source_tag}:official_tweet",
                )
            except Exception as e:
                print(f"[ca_lock] record_lock fail: {e}", flush=True)
            # Immediate single-CA wake (NEVER batch siblings)
            write_fixed_ca_wake(
                it=it,
                ca=ca,
                chain=chain,
                source=f"{source_tag}:official_tweet",
                conf=conf,
                kind="固定CA",
            )
            dry_fire(ca, chain, it, source="today_t20_6551")
            # Official X CA → 已开盘 + stop
            launch_msg = format_launched_msg(it, ca, chain, f"{source_tag}:official_tweet")
            result = mark_launched_official(
                it,
                ca,
                chain,
                evidence=f"T-20 official X tweet CA {ca} via {source_tag}; text={(text[:180])}",
                evidence_url=tweet_url,
            )
            try:
                prev_l = LAUNCH_HISTORY.read_text(encoding="utf-8") if LAUNCH_HISTORY.exists() else ""
            except Exception:
                prev_l = ""
            launch_body = launch_msg + f"\n- mark={json.dumps(result, ensure_ascii=False)[:300]}\n"
            LAUNCH_MSG.write_text(launch_body, encoding="utf-8")  # this CA only
            LAUNCH_HISTORY.write_text((prev_l + ("\n\n" if prev_l.strip() else "") + launch_body), encoding="utf-8")
            emit_alert(
                st,
                it=it,
                kind="today_t20",
                summary=f"【{it.get('name')}】官推固定CA确认 → 已开盘，停止该号推送（其它 T-20 继续）",
                ca=ca,
                chain=chain,
                source=f"{source_tag}:launch",
                confidence="confirmed",
                tweet_url=tweet_url,
            )
            stop_handle_after_fixed(st, it, ca, reason="official_x_ca")
            break
        if hst.get("stopped"):
            break
    hst["seen_tweet_ids"] = sorted(seen_ids)[-200:]
    hst["last_poll"] = iso()
    hst["last_tweet_n"] = len(tweets)


def process_ca_finds(st: dict, it: dict) -> None:
    hl = norm(it.get("handle"))
    hst = st["handles"].setdefault(hl, {})
    if hst.get("stopped"):
        return
    for f in finds_for_handle(it.get("handle") or ""):
        ca = f.get("address") or f.get("ca")
        if not ca:
            continue
        try:  # 2026-10-29 Capta: denied CAs never alert / fix / buy
            from ca_confidence import denied_ca
            if denied_ca(ca):
                continue
        except Exception:
            pass
        kind = str(f.get("kind") or "").lower()
        is_tok = bool(f.get("is_token")) or kind == "token"
        # 炼油：NFT/hybrid 不进高置信与已开盘
        if kind in ("nft", "hybrid_404", "hybrid") or (not is_tok and kind not in ("", "unknown", "contract")):
            if kind == "nft":
                continue
        conf = str(f.get("confidence") or f.get("ca_status") or "")
        # medium+ / high conf alert — require token shape when known
        medium_ok = conf.lower() in ("medium", "high", "confirmed") and f.get("kind") != "wallet" and (is_tok or kind in ("", "unknown"))
        high = (is_high_conf_find(f) or is_official_x_ca(f)) and (is_tok or kind in ("", "unknown"))
        if not (medium_ok or high):
            continue
        key = f"{ca.lower()}|{f.get('ca_status')}|{f.get('detected_at')}"
        seen = set(hst.get("seen_find_keys") or [])
        if key in seen:
            # still check official launch if newly confirmed
            if is_official_x_ca(f) and not hst.get("stopped"):
                pass
            else:
                continue
        seen.add(key)
        hst["seen_find_keys"] = sorted(seen)[-300:]
        chain = f.get("chain") or it.get("chain")
        src = f"ca_finds:{f.get('source') or f.get('provenance') or 'pipeline'}"
        level = "high" if high else conf
        fixed, fixed_why = is_fixed_ca_find(f)
        if medium_ok or high or fixed:
            tag = "固定CA" if fixed else "待确认"
            msg = format_highconf_msg(it, ca, chain, src + f":{fixed_why}", level)
            emit_alert(
                st,
                it=it,
                kind="ca",
                summary=f"【{it.get('name')}】T-20 {tag} · {level} CA `{ca}`（{src} · {fixed_why}）",
                ca=ca,
                chain=chain,
                source=src,
                confidence=("confirmed" if fixed else level),
            )
            if fixed:
                write_fixed_ca_wake(
                    it=it,
                    ca=ca,
                    chain=chain,
                    source=src + f":{fixed_why}",
                    conf=("confirmed" if fixed else level),
                    kind="固定CA",
                )
                dry_fire(ca, chain, it, source="today_t20_fixed_ca")
            hst["last_ca"] = ca
            if fixed:
                try:
                    from ca_confidence import record_lock
                    record_lock(
                        handle=it.get("handle"),
                        name=it.get("name"),
                        address=ca,
                        ca_role="token",
                        post_url=f.get("official_x_url") or f.get("evidence_url") or it.get("tweet_url"),
                        note=f"today_t20:{fixed_why}",
                    )
                except Exception as e:
                    print(f"[ca_lock] record_lock fail: {e}", flush=True)
        if fixed and not hst.get("stopped") and fixed_why in ("official_x", "deployer_or_related"):
            launch_msg = format_launched_msg(it, ca, chain, src)
            result = mark_launched_official(
                it,
                ca,
                chain,
                evidence=f"T-20 fixed CA ({fixed_why}) {ca} via ca_finds",
                evidence_url=f.get("official_x_url") or f.get("evidence_url") or it.get("tweet_url"),
            )
            try:
                prev_l = LAUNCH_HISTORY.read_text(encoding="utf-8") if LAUNCH_HISTORY.exists() else ""
            except Exception:
                prev_l = ""
            launch_body = launch_msg + f"\n- mark={json.dumps(result, ensure_ascii=False)[:300]}\n"
            LAUNCH_MSG.write_text(launch_body, encoding="utf-8")  # this CA only
            LAUNCH_HISTORY.write_text((prev_l + ("\n\n" if prev_l.strip() else "") + launch_body), encoding="utf-8")
            emit_alert(
                st,
                it=it,
                kind="today_t20",
                summary=f"【{it.get('name')}】固定CA（{fixed_why}）确认 → 停止该号推送（其它 T-20 继续）",
                ca=ca,
                chain=chain,
                source=src + ":launch",
                confidence="confirmed",
            )
            stop_handle_after_fixed(st, it, ca, reason=f"fixed_{fixed_why}")
            break
    hst["last_ca_poll"] = iso()


def stop_handle_after_fixed(st: dict, it: dict, ca: str, *, reason: str) -> None:
    """Per-handle stop: one project fixed CA must not block sibling T-20 watches."""
    hl = norm(it.get("handle"))
    hst = st["handles"].setdefault(hl, {})
    hst["stopped"] = True
    hst["stopped_at"] = iso()
    hst["last_ca"] = ca
    hst["stop_reason"] = reason
    # drop from live active list; siblings stay
    active = [h for h in (st.get("active") or []) if norm(h) != hl]
    st["active"] = active
    print(f"[{iso()}] STOP @{it.get('handle')} reason={reason} ca={ca} active_left={active}", flush=True)
    save_state(st)


def ensure_6551_watch(handles: list[str], st: dict) -> None:
    """Best-effort watch_add for T-20 handles (needs plan; ignore failures)."""
    try:
        from sniper_6551 import load_token, watch_add

        tok = load_token()
        if not tok:
            st["wss_watch"] = {"ok": False, "error": "no_token"}
            return
        done = st.setdefault("watch_added", {})
        for h in handles:
            hl = norm(h)
            if done.get(hl):
                continue
            r = watch_add(tok, h, remark="pad-hunter-today-t20")
            done[hl] = {"ok": bool(r.get("ok")), "at": iso(), "http": r.get("http")}
        st["wss_watch"] = {"ok": any(v.get("ok") for v in done.values()), "n": len(done)}
    except Exception as e:
        st["wss_watch"] = {"ok": False, "error": str(e)[:160]}


async def wss_loop(st: dict, handle_map: dict[str, dict]) -> str:
    """One WSS session; routes CA events for T-20 handles. Returns stop reason."""
    try:
        import websockets
    except ImportError:
        return "no_websockets"
    try:
        from sniper_6551 import load_token, extract_ca, WSS_URLS
    except Exception as e:
        return f"import:{e}"

    tok = load_token()
    if not tok:
        return "no_token"
    url = WSS_URLS[0]
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
            st["wss_ok"] = True
            st["mode"] = "wss"
            save_state(st)
            session_started = time.time()
            max_session_s = float(os.environ.get("TODAY_T20_WSS_MAX_SESSION_S", "120"))

            def _sync_handle_map() -> str | None:
                """Refresh T-20 membership mid-session; watch_add new handles (hoodora miss fix)."""
                nonlocal handle_map
                fresh = {
                    norm(it["handle"]): it
                    for it in t20_active(st=st)
                    if not st["handles"].get(norm(it["handle"]), {}).get("stopped")
                }
                old_keys, new_keys = set(handle_map.keys()), set(fresh.keys())
                if old_keys == new_keys:
                    if time.time() - session_started >= max_session_s:
                        st["wss_last_reason"] = "session_cap"
                        save_state(st)
                        return "session_cap"
                    return None
                added = sorted(new_keys - old_keys)
                dropped = sorted(old_keys - new_keys)
                if added:
                    ensure_6551_watch(added, st)
                    print(f"[{iso()}] wss handle_map +{added} -{dropped}", flush=True)
                else:
                    print(f"[{iso()}] wss handle_map -{dropped}", flush=True)
                handle_map.clear()
                handle_map.update(fresh)
                st["active"] = [it.get("handle") for it in fresh.values()]
                st["wss_last_reason"] = "handle_set_changed"
                save_state(st)
                if not handle_map:
                    return "all_stopped"
                # stay on same socket after watch_add; only exit if empty
                return None

            while RUNNING:
                sync_reason = _sync_handle_map()
                if sync_reason:
                    return sync_reason
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=30)
                except asyncio.TimeoutError:
                    try:
                        await ws.ping()
                    except Exception:
                        return "ping_fail"
                    continue
                try:
                    msg = json.loads(raw)
                except Exception:
                    continue
                # pong / subscribe ack
                if msg.get("result") == "pong" or msg.get("method") in (None, "twitter.subscribed"):
                    continue
                params = msg.get("params") or msg.get("data") or {}
                if isinstance(params, dict) and "params" in params and isinstance(params["params"], dict):
                    params = params["params"]
                if not isinstance(params, dict):
                    continue
                # measure 6551 push lag when createdAt present
                try:
                    from datetime import datetime as _dt
                    ca_at = params.get("createdAt") or params.get("created_at")
                    if ca_at:
                        s = str(ca_at).replace("Z", "+00:00")
                        created = _dt.fromisoformat(s)
                        if created.tzinfo is None:
                            from datetime import timezone as _tz
                            created = created.replace(tzinfo=_tz.utc)
                        lag_ms = int((now() - created.astimezone(SH)).total_seconds() * 1000)
                        st["wss_last_lag_ms"] = lag_ms
                        print(f"[{iso()}] wss_lag_ms={lag_ms} @{params.get('twAccount') or params.get('username')}", flush=True)
                except Exception:
                    pass
                tw_acc = (params.get("twAccount") or params.get("username") or "").strip().lstrip("@")
                hl = norm(tw_acc)
                if hl not in handle_map:
                    continue
                it = handle_map[hl]
                hst = st["handles"].setdefault(hl, {})
                if hst.get("stopped"):
                    continue
                ca = extract_ca(params)
                text = ""
                content = params.get("content")
                if isinstance(content, dict):
                    text = str(content.get("text") or "")
                elif isinstance(content, str):
                    text = content
                if not ca:
                    cas = extract_cas_from_text(text)
                    ca = cas[0][0] if cas else None
                if not ca:
                    # non-CA tweet pulse
                    emit_alert(
                        st,
                        it=it,
                        kind="x_post",
                        summary=f"【{it.get('name')}】T-20 WSS 官推：{(text[:100] + '…') if len(text) > 100 else (text or params.get('eventType'))}",
                        source="6551_wss",
                        tweet_url=it.get("tweet_url"),
                    )
                    continue
                # CA event — T-5 优先：推特 WSS 实时推 CA
                is_t5 = in_t5(it)
                source_tag = "6551_wss_t5" if is_t5 else "6551_wss"
                if is_t5:
                    emit_alert(
                        st,
                        it=it,
                        kind="ca",
                        summary=f"【{it.get('name')}】T-5 WSS 实时 CA {ca}",
                        ca=ca,
                        chain=it.get("chain") if it.get("chain") not in (None, "未知") else None,
                        source=source_tag,
                        confidence="high",
                        tweet_url=it.get("tweet_url"),
                    )
                process_tweets(
                    st,
                    it,
                    [
                        {
                            "id": params.get("id") or params.get("content", {}).get("id") if isinstance(params.get("content"), dict) else None,
                            "text": text or f"CA {ca}",
                        }
                    ],
                    source_tag=source_tag,
                )
                save_state(st)
                # refresh map if this handle just stopped (official CA etc.)
                if st["handles"].get(hl, {}).get("stopped"):
                    handle_map.pop(hl, None)
                    if not handle_map:
                        return "all_stopped"
    except Exception as e:
        st["wss_ok"] = False
        st["wss_last_error"] = str(e)[:200]
        return f"err:{type(e).__name__}"
    return "closed"


def cycle_once(st: dict, *, force_rest: bool = False) -> dict:
    """One REST+ca_finds pass over current T-20 set."""
    active = t20_active(st=st)
    write_boost(active)
    summary = {"t20": [it.get("handle") for it in active], "polled": [], "mode": st.get("mode")}
    if not active:
        st["active"] = []
        save_state(st)
        return summary

    handle_map = {norm(it["handle"]): it for it in active}
    ensure_6551_watch([it["handle"] for it in active], st)

    # ca_finds always
    for it in active:
        hl = norm(it["handle"])
        if st["handles"].get(hl, {}).get("stopped"):
            continue
        process_ca_finds(st, it)

    # REST poll: fallback / complement. When WSS is healthy, poll slower to save free-plan PTS.
    now_ts = time.time()
    rest_gap = REST_EVERY
    if st.get("wss_ok") and not force_rest:
        rest_gap = max(REST_EVERY, float(os.environ.get("TODAY_T20_REST_WHEN_WSS", "30")))
    for it in active:
        hl = norm(it["handle"])
        hst = st["handles"].setdefault(hl, {})
        if hst.get("stopped"):
            continue
        last = float(hst.get("_rest_t") or 0)
        if not force_rest and (now_ts - last) < rest_gap:
            continue
        tweets, meta = rest_poll_handle(it["handle"], n=5)
        hst["_rest_t"] = now_ts
        hst["rest_meta"] = meta
        if meta.get("ok"):
            process_tweets(st, it, tweets, source_tag="6551_rest")
            summary["polled"].append(it["handle"])
        elif meta.get("quota_or_plan"):
            st["mode"] = st.get("mode") or "rest_blocked"
            st["rest_block"] = meta
            # don't hammer quota
            hst["_rest_t"] = now_ts + 60
        # enter/pulse alert once per window
        if not hst.get("entered_alert"):
            emit_alert(
                st,
                it=it,
                kind="today_t20",
                summary=f"【{it.get('name')}】进入 T-20 高频窗口（开盘前{int(T20_MIN)}分钟）· 6551+CA 提频",
                source="t20_enter",
                confidence="info",
            )
            hst["entered_alert"] = True
            hst["entered_at"] = iso()

    st["active"] = [it.get("handle") for it in active if not st["handles"].get(norm(it["handle"]), {}).get("stopped")]
    st["last_cycle"] = iso()
    save_state(st)
    return summary


def run_loop(*, prefer_wss: bool = True) -> None:
    global RUNNING

    def _stop(*_a):
        global RUNNING
        RUNNING = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    st = load_state()
    st["started_at"] = iso()
    st["mode"] = "rest"
    save_state(st)
    print(f"[{iso()}] today_t20_watch start tick={TICK}s rest_every={REST_EVERY}s t20={T20_MIN}m t5={T5_MIN}m wss_realtime_ca dry_run sniper", flush=True)

    wss_backoff = 1.0
    while RUNNING:
        try:
            active = t20_active(st=st)
            write_boost(active)
            if not active:
                st = load_state()
                st["active"] = []
                st["idle"] = True
                save_state(st)
                time.sleep(min(TICK * 3, 15))
                continue

            st = load_state()
            st["idle"] = False
            # REST + ca_finds cycle
            summary = cycle_once(st)
            print(f"[{iso()}] cycle t20={summary.get('t20')} polled={summary.get('polled')} mode={st.get('mode')} wss_ok={st.get('wss_ok')}", flush=True)

            # 推特 WSS：T-60 开；T-5 强制实时（断线 0.5s 重连）
            t5 = t5_active(st=st)
            if t5:
                for it in t5:
                    hl = norm(it["handle"])
                    hst = st["handles"].setdefault(hl, {})
                    if not hst.get("t5_entered"):
                        hst["t5_entered"] = iso()
                        emit_alert(
                            st,
                            it=it,
                            kind="today_t5",
                            summary=f"【{it.get('name')}】进入 T-5：推特 WSS 实时推 CA（开盘前{int(T5_MIN)}分钟）",
                            source="today_t5",
                        )
                save_state(st)

            if prefer_wss and RUNNING:
                handle_map = {
                    norm(it["handle"]): it
                    for it in t20_active(st=st)
                    if not st["handles"].get(norm(it["handle"]), {}).get("stopped")
                }
                if handle_map:
                    ensure_6551_watch(list(handle_map.keys()), st)
                    try:
                        reason = asyncio.run(wss_loop(st, handle_map))
                    except Exception as e:
                        reason = f"async:{e}"
                    st = load_state()
                    st["wss_last_reason"] = reason
                    st["t5_active"] = [it.get("handle") for it in t5_active(st=st)]
                    if reason in ("session_cap", "handle_set_changed", "all_stopped"):
                        # healthy rotate — pick up new T-20 handles immediately
                        wss_backoff = 1.0
                        st["mode"] = "wss_t5" if t5_active(st=st) else "wss"
                        save_state(st)
                    elif reason in ("no_websockets",) or str(reason).startswith("err:") or reason in ("no_token", "ping_fail", "closed"):
                        st["wss_ok"] = False
                        st["mode"] = "rest"
                        save_state(st)
                        # T-5: reconnect ASAP
                        delay = 0.5 if t5_active(st=st) else min(wss_backoff, 30)
                        time.sleep(delay)
                        if not t5_active(st=st):
                            wss_backoff = min(wss_backoff * 2, 30)
                    else:
                        wss_backoff = 1.0
                        st["mode"] = "wss_t5" if t5_active(st=st) else "wss"
                        save_state(st)
            time.sleep(0.5 if t5_active(st=st) else TICK)
        except Exception as e:
            print(f"[{iso()}] ERR {e}", flush=True)
            time.sleep(5)


def cmd_status() -> int:
    st = load_state()
    active = t20_active(st=st)
    upcoming = []
    ref = now()
    for it in today_items():
        dt = parse_dt(it.get("listing_at"))
        if not dt:
            continue
        t20_start = dt - timedelta(minutes=T20_MIN)
        t5_start = dt - timedelta(minutes=T5_MIN)
        upcoming.append(
            {
                "handle": it.get("handle"),
                "name": it.get("name"),
                "listing_at": it.get("listing_at"),
                "t20_starts_at": iso(t20_start),
                "t5_starts_at": iso(t5_start),
                "in_t20": in_t20(it, ref, st=st),
                "in_t5": in_t5(it, ref, st=st),
                "t20_after_minutes": T20_AFTER_MIN,
                "minutes_to_t20": round((t20_start - ref).total_seconds() / 60.0, 1),
                "minutes_to_t5": round((t5_start - ref).total_seconds() / 60.0, 1),
                "minutes_to_listing": round((dt - ref).total_seconds() / 60.0, 1),
                "stopped": bool(st.get("handles", {}).get(norm(it.get("handle")), {}).get("stopped")),
            }
        )
    print(
        json.dumps(
            {
                "now": iso(ref),
                "mode": st.get("mode"),
                "wss_ok": st.get("wss_ok"),
                "active_t20": [it.get("handle") for it in active],
                "active_t5": [it.get("handle") for it in t5_active(ref, st=st)],
                "t5_window_minutes": T5_MIN,
                "t20_after_minutes": T20_AFTER_MIN,
                "t20_keep_after_h": T20_KEEP_AFTER_H,
                "wake_queue": str(WAKE_QUEUE),
                "upcoming": upcoming,
                "state_updated_at": st.get("updated_at"),
                "dry_run": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def cmd_once() -> int:
    st = load_state()
    summary = cycle_once(st, force_rest=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def cmd_inject(*, handle: str, ca: str, chain: str | None = None, official: bool = True) -> int:
    """Smoke: pretend a T-20 high-conf CA (and optional official launch)."""
    items = {norm(it["handle"]): it for it in today_items()}
    it = items.get(norm(handle))
    if not it:
        # synthetic item for smoke if not on list
        it = {"handle": handle.lstrip("@"), "name": handle, "listing_at": iso(now() + timedelta(minutes=10)), "chain": chain or "bsc"}
    st = load_state()
    msg = format_highconf_msg(it, ca, chain or it.get("chain"), "inject", "high")
    emit_alert(
        st,
        it=it,
        kind="ca",
        summary=f"【{it.get('name')}】T-20 inject CA `{ca}`",
        ca=ca,
        chain=chain or it.get("chain"),
        source="inject",
        confidence="high",
    )
    MSG.write_text(msg + "\n", encoding="utf-8")
    fire = dry_fire(ca, chain or it.get("chain"), it, source="today_t20_inject")
    result = None
    if official:
        # do NOT actually force_launch on random inject unless --official and handle on today list
        # For smoke use official=False by default in CLI; when True, mark launched
        result = mark_launched_official(
            it,
            ca,
            chain or it.get("chain"),
            evidence=f"inject smoke official CA {ca}",
            evidence_url=it.get("tweet_url"),
        )
        LAUNCH_MSG.write_text(format_launched_msg(it, ca, chain, "inject") + "\n", encoding="utf-8")
    save_state(st)
    print(json.dumps({"alert": True, "fire": {k: fire.get(k) for k in ("action", "ms", "would_buy", "skipped_reason", "dry_run") if k in fire or True}, "launch": result}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="今日项目清单 T-20 高频 CA")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("status")
    sub.add_parser("once")
    p_watch = sub.add_parser("watch")
    p_watch.add_argument("--no-wss", action="store_true")
    p_inj = sub.add_parser("inject")
    p_inj.add_argument("--handle", required=True)
    p_inj.add_argument("--ca", required=True)
    p_inj.add_argument("--chain", default="bsc")
    p_inj.add_argument("--official", action="store_true", help="Also force_launch + drop (destructive)")
    p_sched = sub.add_parser("schedule")  # print T-20 windows

    args = ap.parse_args(argv)
    cmd = args.cmd or "status"
    if cmd == "status":
        return cmd_status()
    if cmd == "once":
        return cmd_once()
    if cmd == "watch":
        run_loop(prefer_wss=not args.no_wss)
        return 0
    if cmd == "inject":
        return cmd_inject(handle=args.handle, ca=args.ca, chain=args.chain, official=args.official)
    if cmd == "schedule":
        return cmd_status()
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
