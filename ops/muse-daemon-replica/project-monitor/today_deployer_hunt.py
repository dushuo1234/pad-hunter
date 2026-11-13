#!/usr/bin/env python3
"""今日项目清单 · 部署者猎取 → 尽早钉住代币 CA（非 NFT）。

adu 2026-10-28：针对今日清单不定时拉取部署者 / 关联钱包 / 工厂部署信息，
有些团队会在开盘前就把代币部署好。

范围：仅 today_projects.json 的 handles。
流程：
  1) 汇总钱包：wallet_watchlist / watched_wallets / ca_finds(kind=wallet)
  2) 已知合约（ca_finds / watchlist.ca）：解析 creator → 加入监控钱包
  3) 有官网则轻量抓 0x（钱包进猎取，代币走 ca_gate）
  4) 对钱包跑 trace_wallet_ca（CREATE / CREATE2 / factory）
  5) ca_gate.is_token 才算钉住：写 TRACE 事件、可选 rebuild ca_finds、
     workbench alert + alerts/today_deployer_hunt_alerts.jsonl +
     _today_deployer_hunt_msg.txt；仅「固定CA」(部署者/关联钱包) 才 sniper dry_run+锁；站点/reverify 仍待确认；不直推电报（归扫描）

频率（Asia/Shanghai，按最近 listing_at）：
  >2h / 无时间 → 默认 10min；≤2h → 3min；≤20min（T-20）→ 60s
绝不编造 listing_at / CA；NFT≠token。
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
sys.path.insert(0, str(BASE))

SH = ZoneInfo("Asia/Shanghai")
TODAY = BASE / "today_projects.json"
WATCHLIST = BASE / "watchlist.json"
WALLET_WL = BASE / "wallet_watchlist.json"
CA_FINDS = BASE / "ca_finds.json"
STATE = BASE / "alerts" / "today_deployer_hunt_state.json"
ALERTS = BASE / "alerts" / "today_deployer_hunt_alerts.jsonl"
SOON = BASE / "alerts" / "workbench_soon.jsonl"
MSG = BASE / "_today_deployer_hunt_msg.txt"
STATUS_JSON = BASE / "alerts" / "today_deployer_hunt_status.json"
CREATOR_CACHE = BASE / "alerts" / "today_deployer_creator_cache.json"

EVM_RE = re.compile(r"(?<![a-fA-F0-9])(0x[a-fA-F0-9]{40})(?![a-fA-F0-9])")
ZERO = "0x0000000000000000000000000000000000000000"

# interval seconds by proximity to listing
INTERVAL_FAR = float(os.environ.get("TODAY_DEPLOYER_FAR", "300"))       # >2h
INTERVAL_NEAR = float(os.environ.get("TODAY_DEPLOYER_NEAR", "90"))     # ≤2h
INTERVAL_T20 = float(os.environ.get("TODAY_DEPLOYER_T20", "20"))        # ≤20m
INTERVAL_NO_TIME = float(os.environ.get("TODAY_DEPLOYER_NOTIME", "900"))
T20_MIN = float(os.environ.get("TODAY_T20_MINUTES", "60"))
NEAR_H = float(os.environ.get("TODAY_DEPLOYER_NEAR_H", "4"))

RUNNING = True
UA = "PadHunterTodayDeployerHunt/1.0"
TOKEN_FILE = BASE / "workbench_api_token.txt"
API = os.environ.get("PAD_HUNTER_CF_API", "https://api.adualpha.win").rstrip("/")

# free / keyed explorers for getcontractcreation
BLOCKSCOUT = {
    "ethereum": "https://eth.blockscout.com/api",
    "ink": "https://explorer.inkonchain.com/api",
}
ETHERSCAN_V2 = "https://api.etherscan.io/v2/api"
CHAIN_IDS = {
    "ethereum": 1, "base": 8453, "bsc": 56, "hyperevm": 999,
    "robinhood": 4663, "ink": 57073,
}


def now() -> datetime:
    return datetime.now(SH)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def norm_h(h: str | None) -> str:
    return (h or "").lstrip("@").strip().lower()


def norm_a(a: str | None) -> str:
    if not a:
        return ""
    a = str(a).strip()
    return a.lower() if a.lower().startswith("0x") else a


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def dump_json(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_state() -> dict:
    st = load_json(STATE, {})
    if not isinstance(st, dict):
        st = {}
    st.setdefault("dedupe", {})
    st.setdefault("handles", {})
    st.setdefault("last_cycle_at", None)
    st.setdefault("last_interval_s", None)
    return st


def save_state(st: dict) -> None:
    st["updated_at"] = iso()
    dump_json(STATE, st)


def today_items() -> list[dict]:
    doc = load_json(TODAY, {})
    return [it for it in (doc.get("items") or []) if isinstance(it, dict) and it.get("handle")]


def parse_listing(it: dict) -> datetime | None:
    raw = it.get("listing_at") or it.get("listing_at_display")
    if not raw:
        return None
    try:
        s = str(raw).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=SH)
        return dt.astimezone(SH)
    except Exception:
        return None


def pick_interval(items: list[dict]) -> float:
    """Shortest interval among today items (boost near listing)."""
    if not items:
        return INTERVAL_FAR
    best = INTERVAL_FAR
    n = now()
    any_time = False
    for it in items:
        dt = parse_listing(it)
        if dt is None:
            continue
        any_time = True
        secs = (dt - n).total_seconds()
        if secs < -300:
            # already past; still poll gently until dropped from today list
            best = min(best, INTERVAL_NEAR)
            continue
        if secs <= T20_MIN * 60:
            best = min(best, INTERVAL_T20)
        elif secs <= NEAR_H * 3600:
            best = min(best, INTERVAL_NEAR)
        else:
            best = min(best, INTERVAL_FAR)
    if not any_time:
        return INTERVAL_NO_TIME
    return best


def _curl_json(url: str, timeout: int = 18) -> dict | list | None:
    try:
        out = subprocess.check_output(
            ["curl", "-sS", "--max-time", str(timeout), "-H", f"user-agent: {UA}", url],
            text=True, stderr=subprocess.DEVNULL,
        )
        return json.loads(out)
    except Exception:
        return None


def _etherscan_key() -> str | None:
    try:
        from funding_links import _etherscan_api_key
        return _etherscan_api_key()
    except Exception:
        pass
    for p in (BASE / ".etherscan_api_key",):
        try:
            if p.is_file():
                v = p.read_text(encoding="utf-8").strip().splitlines()[0].strip()
                if v and not v.startswith("#"):
                    return v
        except Exception:
            continue
    return None


def resolve_creator(addr: str, chain_hint: str | None = None) -> dict | None:
    """Return {creator, chain, tx_hash, evidence_url, via} or None. Never invent."""
    a = norm_a(addr)
    if not a.startswith("0x") or len(a) != 42 or a == ZERO:
        return None
    cache = load_json(CREATOR_CACHE, {})
    ck = f"{(chain_hint or 'any').lower()}:{a}"
    hit = cache.get(ck) or cache.get(f"any:{a}")
    if isinstance(hit, dict) and hit.get("creator"):
        return hit
    if isinstance(hit, dict) and hit.get("miss") and time.time() - hit.get("_ts", 0) < 3600:
        return None

    chains = []
    if chain_hint and chain_hint.lower() not in ("未知", "evm", "unknown", ""):
        chains.append(chain_hint.lower())
    for c in ("ethereum", "bsc", "base", "robinhood", "ink", "hyperevm"):
        if c not in chains:
            chains.append(c)

    key = _etherscan_key()
    for ch in chains:
        # 1) free Blockscout
        api = BLOCKSCOUT.get(ch)
        if api:
            r = _curl_json(f"{api}?module=contract&action=getcontractcreation&contractaddresses={a}")
            res = None
            if isinstance(r, dict):
                raw = r.get("result")
                if isinstance(raw, list) and raw:
                    res = raw[0]
                elif isinstance(raw, dict):
                    res = raw
            if isinstance(res, dict):
                creator = norm_a(res.get("contractCreator") or res.get("creatorAddress") or res.get("from"))
                tx = res.get("txHash") or res.get("hash")
                if creator and creator.startswith("0x") and creator != ZERO:
                    out = {
                        "creator": creator,
                        "chain": ch,
                        "tx_hash": tx,
                        "evidence_url": f"https://etherscan.io/tx/{tx}" if ch == "ethereum" and tx else None,
                        "via": "blockscout_getcontractcreation",
                        "_ts": time.time(),
                    }
                    cache[ck] = out
                    cache[f"any:{a}"] = out
                    dump_json(CREATOR_CACHE, cache)
                    return out
        # 2) Etherscan V2 (key; may be paid for some chains — fail soft)
        if key and ch in CHAIN_IDS:
            cid = CHAIN_IDS[ch]
            url = (
                f"{ETHERSCAN_V2}?chainid={cid}&module=contract&action=getcontractcreation"
                f"&contractaddresses={a}&apikey={key}"
            )
            r = _curl_json(url)
            res = None
            if isinstance(r, dict):
                raw = r.get("result")
                if isinstance(raw, list) and raw:
                    res = raw[0]
                elif isinstance(raw, dict):
                    res = raw
                # rate-limit / paid → skip quietly
                msg = str(r.get("message") or r.get("result") or "").lower()
                if "free api" in msg or "invalid api" in msg or "not supported" in msg:
                    continue
            if isinstance(res, dict):
                creator = norm_a(res.get("contractCreator") or res.get("creatorAddress") or res.get("from"))
                tx = res.get("txHash") or res.get("hash")
                if creator and creator.startswith("0x") and creator != ZERO:
                    out = {
                        "creator": creator,
                        "chain": ch,
                        "tx_hash": tx,
                        "evidence_url": None,
                        "via": "etherscan_v2_getcontractcreation",
                        "_ts": time.time(),
                    }
                    cache[ck] = out
                    cache[f"any:{a}"] = out
                    dump_json(CREATOR_CACHE, cache)
                    return out

    cache[ck] = {"miss": True, "_ts": time.time()}
    dump_json(CREATOR_CACHE, cache)
    return None


def fetch_site_addrs(url: str) -> list[str]:
    if not url or not str(url).startswith("http"):
        return []
    try:
        from scan_listing_ca import fetch_site, extract_evm
        fr = fetch_site(url)
        text = (fr.get("text") or "") if isinstance(fr, dict) else ""
        if not text:
            return []
        return [norm_a(c.get("address")) for c in extract_evm(text) if c.get("address")]
    except Exception:
        try:
            out = subprocess.check_output(
                ["curl", "-sS", "-L", "--max-time", "20", "-A", UA, url],
                text=True, stderr=subprocess.DEVNULL,
            )
            return [norm_a(m.group(1)) for m in EVM_RE.finditer(out or "")]
        except Exception:
            return []


def classify(addr: str, chain_hint: str | None = None) -> dict:
    try:
        from ca_gate import verify_address
        return verify_address(addr, chain_hint=chain_hint) or {}
    except Exception as e:
        return {"address": addr, "kind": "unknown", "is_token": False, "error": str(e)[:120]}


def collect_wallets_for(it: dict) -> dict:
    """Return {wallets: [{address,chain,source,confidence}], known_addrs: [...], site_tokens: [...]}."""
    h = norm_h(it.get("handle"))
    name = it.get("name") or it.get("handle")
    wallets: dict[str, dict] = {}
    known: list[dict] = []
    site_tokens: list[dict] = []

    def add_w(addr, *, chain=None, source=None, confidence="medium", note=None):
        a = norm_a(addr)
        if not a.startswith("0x") or len(a) != 42 or a == ZERO:
            return
        cur = wallets.get(a)
        row = {
            "address": a,
            "chain": chain or it.get("chain"),
            "source": source,
            "confidence": confidence,
            "note": note,
            "handle": h,
            "project": name,
        }
        if not cur:
            wallets[a] = row
        else:
            # keep higher confidence
            rank = {"low": 0, "medium": 1, "high": 2}
            if rank.get(str(confidence), 0) > rank.get(str(cur.get("confidence")), 0):
                cur["confidence"] = confidence
            if source and source not in (cur.get("sources") or []):
                cur.setdefault("sources", [cur.get("source")]).append(source)

    # 1) wallet_watchlist
    ww = load_json(WALLET_WL, {})
    for w in ww.get("wallets") or []:
        if norm_h(w.get("handle")) != h:
            continue
        add_w(w.get("address") or w.get("wallet"), chain=w.get("chain"),
              source="wallet_watchlist", confidence=w.get("confidence") or "medium",
              note=w.get("note"))

    # 2) watched_wallets
    try:
        import watched_wallets as wwmod
        rows = wwmod.active(wwmod.load().get("wallets") or [])
        for w in rows:
            if norm_h(w.get("handle")) != h:
                continue
            add_w(w.get("wallet"), chain=w.get("chain"),
                  source=f"watched_wallets:{w.get('source')}",
                  confidence=w.get("confidence") or "medium")
    except Exception:
        pass

    # 3) ca_finds (wallets + known contracts/tokens)
    cf = load_json(CA_FINDS, {})
    for f in cf.get("finds") or []:
        if norm_h(f.get("handle")) != h:
            continue
        addr = f.get("address") or f.get("ca")
        if not addr:
            continue
        kind = str(f.get("kind") or "").lower()
        known.append({
            "address": norm_a(addr),
            "chain": f.get("chain"),
            "kind": kind,
            "is_token": bool(f.get("is_token")),
            "source": "ca_finds",
            "ca_status": f.get("ca_status"),
        })
        if kind == "wallet" or (not f.get("is_token") and kind in ("", "unknown") and "wallet" in str(f.get("note") or "").lower()):
            add_w(addr, chain=f.get("chain"), source="ca_finds:wallet",
                  confidence=f.get("confidence") or "medium")
        # traced_from / creator fields
        for fld in ("traced_from", "creator", "deployer", "wallet"):
            if f.get(fld):
                add_w(f.get(fld), chain=f.get("chain"), source=f"ca_finds:{fld}",
                      confidence="medium")

    # 4) watchlist.ca
    wl = load_json(WATCHLIST, {})
    items = wl if isinstance(wl, list) else wl.get("projects") or wl.get("items") or []
    for p in items:
        if norm_h(p.get("handle")) != h:
            continue
        if p.get("ca"):
            known.append({
                "address": norm_a(p.get("ca")),
                "chain": p.get("ca_chain") or p.get("chain"),
                "kind": "watchlist.ca",
                "is_token": None,
                "source": p.get("ca_source") or "watchlist.ca",
            })
        for fld in ("deployer", "creator", "team_wallet"):
            if p.get(fld):
                add_w(p.get(fld), chain=p.get("chain"), source=f"watchlist:{fld}",
                      confidence="medium")

    # 5) site scrape
    site = it.get("site")
    if site:
        for addr in fetch_site_addrs(site):
            v = classify(addr, it.get("chain"))
            kind = str(v.get("kind") or "unknown").lower()
            if v.get("is_token") or kind == "token":
                site_tokens.append({
                    "address": norm_a(addr),
                    "chain": v.get("chain") or it.get("chain"),
                    "kind": "token",
                    "is_token": True,
                    "source": f"site:{site}",
                    "verify": v,
                })
            elif kind == "wallet":
                add_w(addr, chain=v.get("chain") or it.get("chain"),
                      source=f"site:{site}", confidence="low", note="site scrape EOA")
            elif kind in ("contract", "unknown", "nft", "hybrid_404"):
                known.append({
                    "address": norm_a(addr),
                    "chain": v.get("chain") or it.get("chain"),
                    "kind": kind,
                    "is_token": bool(v.get("is_token")),
                    "source": f"site:{site}",
                })

    # 6) resolve creators of known contracts → wallets
    for k in known:
        if k.get("is_token") is False and k.get("kind") == "wallet":
            continue
        # skip pure EOAs
        if k.get("kind") == "wallet":
            continue
        cre = resolve_creator(k["address"], k.get("chain") or it.get("chain"))
        if cre and cre.get("creator"):
            add_w(
                cre["creator"],
                chain=cre.get("chain") or k.get("chain"),
                source=f"creator_of:{k['address'][:10]}",
                confidence="medium",
                note=f"getcontractcreation via {cre.get('via')}",
            )
            # persist into watched_wallets (medium; never invent high)
            try:
                import watched_wallets as wwmod
                row = wwmod.make_row(
                    handle=h,
                    chain=cre.get("chain") or k.get("chain") or "evm",
                    wallet=cre["creator"],
                    source="scan",
                    confidence="medium",
                    evidence_url=cre.get("evidence_url") or it.get("tweet_url"),
                    added_at=iso(),
                    listing_at=it.get("listing_at"),
                )
                doc = wwmod.load()
                merged = wwmod.merge(doc.get("wallets") or [], [row])
                wwmod.save(merged)
            except Exception:
                pass

    return {
        "wallets": list(wallets.values()),
        "known_addrs": known,
        "site_tokens": site_tokens,
    }


def persist_wallet_watchlist(it: dict, wallets: list[dict]) -> None:
    """Merge newly found wallets into wallet_watchlist.json (incremental)."""
    if not wallets:
        return
    try:
        from build_wallet_watchlist import build as _rebuild  # full rebuild is OK but heavy
    except Exception:
        _rebuild = None
    # light merge into existing file
    doc = load_json(WALLET_WL, {})
    existing = {(norm_h(w.get("handle")), norm_a(w.get("address") or w.get("wallet"))): w
                for w in (doc.get("wallets") or [])}
    changed = False
    for w in wallets:
        key = (norm_h(it.get("handle")), norm_a(w.get("address")))
        if not key[1]:
            continue
        if key not in existing:
            existing[key] = {
                "address": key[1],
                "address_norm": key[1],
                "chain": w.get("chain") or "evm",
                "confidence": w.get("confidence") or "medium",
                "eoa_confirmed": False,
                "sources": [w.get("source") or "today_deployer_hunt"],
                "note": w.get("note") or "today_deployer_hunt",
                "evidence_url": it.get("tweet_url") or it.get("site"),
                "first_seen": iso(),
                "last_seen": iso(),
                "project": it.get("name") or it.get("handle"),
                "handle": norm_h(it.get("handle")),
            }
            changed = True
        else:
            existing[key]["last_seen"] = iso()
            src = w.get("source")
            if src and src not in (existing[key].get("sources") or []):
                existing[key].setdefault("sources", []).append(src)
                changed = True
    if changed:
        rows = list(existing.values())
        doc["wallets"] = rows
        doc["wallet_count"] = len(rows)
        doc["generated_at"] = iso()
        doc["timezone"] = "Asia/Shanghai"
        dump_json(WALLET_WL, doc)


def trace_wallets(it: dict, wallets: list[dict], *, force_recent: bool) -> list[dict]:
    """Run scoped wallet traces; return list of deployed contract rows with handle."""
    if not wallets:
        return []
    try:
        import trace_wallet_ca as tw
    except Exception as e:
        print(f"[hunt] trace import fail: {e}", flush=True)
        return []

    deployed_all: list[dict] = []
    h = norm_h(it.get("handle"))
    # Prefer one-shot per address via run(only_address=...) to avoid rewriting global latest with partial set
    factories = tw.load_json(tw.FACTORIES, {})
    rpcs = tw.pick_rpcs(factories)
    recent = 400 if force_recent else 0

    for w in wallets:
        addr = w.get("address")
        if not addr:
            continue
        find = {
            "project": it.get("name") or it.get("handle"),
            "handle": it.get("handle"),
            "chain": w.get("chain") or it.get("chain") or "evm",
            "address": addr,
            "confidence": w.get("confidence") or "medium",
            "source": w.get("source") or "today_deployer_hunt",
            "note": w.get("note") or "today_deployer_hunt",
        }
        try:
            print(f"  [hunt] trace @{h} {addr[:12]}…", flush=True)
            r = tw.trace_one(find, rpcs, factories, recent_window=recent, force_recent=force_recent)
        except Exception as e:
            print(f"  [hunt] trace err {addr[:12]}: {e}", flush=True)
            continue
        clf = r.get("classification") or {}
        # If address is itself a contract, skip deploy hunt on it (creator path handles it)
        if clf.get("kind") == "contract":
            continue
        for d in r.get("deployed") or []:
            ca = d.get("contract")
            if not ca:
                continue
            deployed_all.append({
                "address": norm_a(ca),
                "chain": d.get("chain") or clf.get("chain") or w.get("chain"),
                "wallet": addr,
                "tx_hash": d.get("tx_hash"),
                "evidence_url": d.get("evidence_url"),
                "via": d.get("via"),
                "note": d.get("note"),
                "factory_id": d.get("factory_id"),
                "handle": it.get("handle"),
                "project": it.get("name"),
                "source": f"wallet_trace:{addr}",
            })
    return deployed_all


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
        token = ""
        if TOKEN_FILE.is_file():
            token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        payload = json.dumps({"alerts": [rec], "client_id": "box-today-deployer-hunt"})
        cmd = [
            "curl", "-sS", "--max-time", "12",
            "-X", "POST", f"{API}/v1/workbench/alert",
            "-H", "content-type: application/json",
            "-H", f"user-agent: {UA}",
            "-d", payload,
        ]
        if token:
            cmd.extend(["-H", f"authorization: Bearer {token}"])
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        rec["_push"] = {"body": out[:200]}
    except Exception as e:
        rec["_push"] = {"error": str(e)[:160]}


def dry_fire(ca: str, chain: str | None, it: dict, source: str, *, find: dict | None = None) -> dict:
    """Only fire when 固定CA (deployer/related or official)."""
    find = dict(find or {})
    find.setdefault("address", ca)
    find.setdefault("chain", chain or it.get("chain"))
    find.setdefault("handle", it.get("handle"))
    find.setdefault("name", it.get("name"))
    find.setdefault("source", source)
    find.setdefault("is_token", True)
    find.setdefault("kind", "token")
    try:
        from ca_confidence import is_ca_fixed
        ok, why = is_ca_fixed(find)
    except Exception as e:
        return {"ok": False, "skipped_reason": f"is_ca_fixed_err:{e}", "would_buy": False}
    if not ok:
        return {"action": "skipped", "skipped_reason": f"not_fixed_ca:{why}", "would_buy": False}
    try:
        from sniper_buy import fire_buy
        return fire_buy(
            ca=ca,
            chain=str(chain or it.get("chain") or "bsc"),
            project=it.get("name") or it.get("handle"),
            handle=it.get("handle"),
            source=source,
            extra={"layer": "today_deployer_hunt", "listing_at": it.get("listing_at"), "ca_fixed": True, "ca_fixed_reason": why},
        )
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def format_msg(it: dict, ca: str, chain: str | None, source: str, conf: str, *, wallet: str | None = None, fixed: bool = False, fixed_why: str = "") -> str:
    tag = "固定CA" if fixed else "待确认"
    lines = [
        f"🧲 今日部署者猎取 · {tag} · {conf} · {it.get('name')}（@{it.get('handle')}）",
        f"- CA：`{ca}`" + (f"（{chain}）" if chain else ""),
        f"- 开盘：{it.get('listing_at_display') or it.get('listing_at') or '—'}（Asia/Shanghai）",
        f"- 来源：{source}" + (f" · {fixed_why}" if fixed_why else ""),
        f"- 状态：{tag}（炼油：官推或部署者/关联钱包才固定）",
    ]
    if wallet:
        lines.append(f"- 部署者/关联钱包：`{wallet}`")
    if fixed:
        lines.append("- sniper：dry_run（不实买）")
    else:
        lines.append("- sniper：跳过（未固定）")
    lines.append(f"- 官网：{it.get('site') or '—'}")
    lines.append("- 电报：归扫描/DeepSeek（本路径不直推；仅固定CA可推）")
    return "\n".join(lines)


def emit_token(
    st: dict,
    it: dict,
    *,
    ca: str,
    chain: str | None,
    source: str,
    conf: str = "high",
    wallet: str | None = None,
    verify: dict | None = None,
    rebuild: bool = True,
) -> bool:
    """Dedupe + alert; dry_fire/record_lock only when 固定CA. NFT filtered by caller."""
    h = norm_h(it.get("handle"))
    dk = f"deployer_hunt|token|{h}|{norm_a(ca)}"
    if dk in st.setdefault("dedupe", {}):
        return False
    st["dedupe"][dk] = iso()
    if len(st["dedupe"]) > 4000:
        keys = list(st["dedupe"].keys())
        for k in keys[: len(keys) - 2000]:
            st["dedupe"].pop(k, None)

    find = {
        "address": ca,
        "chain": chain or it.get("chain"),
        "handle": it.get("handle"),
        "name": it.get("name"),
        "source": source,
        "is_token": True,
        "kind": "token",
        "traced_from": wallet,
        "deployer": wallet,
        "creator": wallet,
        "wallet_watched": bool(wallet),
        "deployer_watched": bool(wallet),
        "related_wallet": bool(wallet),
        "confidence": conf,
    }
    if wallet and ("wallet_trace" in str(source) or "watch" in str(source).lower() or "trace" in str(source).lower()):
        find["source"] = f"wallet_watch:{source}"
    try:
        from ca_confidence import is_ca_fixed
        fixed, fixed_why = is_ca_fixed(find)
    except Exception:
        fixed, fixed_why = (bool(wallet), "deployer_or_related" if wallet else "candidate_not_fixed")

    msg = format_msg(it, ca, chain, source, conf, wallet=wallet, fixed=fixed, fixed_why=fixed_why)
    if fixed:
        try:
            MSG.write_text(msg + "\n", encoding="utf-8")
        except Exception:
            pass

    rec = {
        "id": hashlib.sha1(dk.encode()).hexdigest()[:16],
        "ts": iso(),
        "handle": it.get("handle"),
        "name": it.get("name"),
        "kind": "ca",
        "today_deployer_hunt": True,
        "listing_at": it.get("listing_at"),
        "listing_at_display": it.get("listing_at_display"),
        "summary": msg.split("\n")[0],
        "address": ca,
        "ca": ca,
        "chain": chain or it.get("chain"),
        "source": source,
        "confidence": ("confirmed" if fixed else conf),
        "ca_fixed": fixed,
        "ca_fixed_reason": fixed_why,
        "ca_status": ("confirmed" if fixed else "candidate"),
        "wallet": wallet,
        "is_token": True,
        "verify": {k: (verify or {}).get(k) for k in ("kind", "is_token", "label_zh", "note_zh", "decimals", "chain") if k in (verify or {})},
        "tweet_url": it.get("tweet_url"),
        "site": it.get("site"),
        "client_tag": "today_deployer_hunt",
    }
    append_alert(rec)
    push_workbench(rec)
    try:
        from today_ca_push import push_event, chain_note, norm_chain
        ch = norm_chain(rec.get("chain"))
        ca_s = (rec.get("ca") or "").strip()
        push_event(
            {
                "id": rec.get("id") or "",
                "handle": rec.get("handle"),
                "name": rec.get("name"),
                "ca": ca_s,
                "chain": ch,
                "chain_note": chain_note(ch, ca_s),
                "wallet_note": chain_note(ch, ca_s),
                "ts": rec.get("ts"),
                "confidence": rec.get("confidence"),
                "ca_fixed": rec.get("ca_fixed"),
                "ca_fixed_reason": rec.get("ca_fixed_reason"),
                "ca_status": rec.get("ca_status"),
                "is_token": True,
                "kind": "ca",
                "source": rec.get("source") or "today_deployer_hunt",
                "evidence_url": rec.get("tweet_url") or rec.get("site"),
                "client_id": "box-today-deployer-hunt",
            }
        )
    except Exception as e:
        print(f"[hunt] today_ca_push: {e}", flush=True)
    if fixed:
        dry_fire(ca, chain, it, source=f"today_deployer_hunt:{source}", find=find)
        try:
            from ca_confidence import record_lock
            record_lock(
                handle=it.get("handle"),
                name=it.get("name"),
                address=ca,
                ca_role="token",
                post_url=it.get("tweet_url"),
                note=f"today_deployer_hunt:{fixed_why}:{source}",
            )
        except Exception as e:
            print(f"[hunt] record_lock fail: {e}", flush=True)
    print(f"[{rec['ts']}] {'FIXED' if fixed else 'CAND'} @{it.get('handle')} {ca} via {source} ({fixed_why})", flush=True)

    # Emergency TG only if fixed + explicitly enabled (扫描 owns TG by default)
    if fixed and os.environ.get("TODAY_TG_BY_HUNT") == "1":
        try:
            from telegram_today_only import push_ca
            push_ca(
                handle=it.get("handle") or "",
                name=it.get("name"),
                ca=ca,
                chain=chain or it.get("chain"),
                kind="ca",
                summary=rec["summary"],
                listing_at=it.get("listing_at_display") or it.get("listing_at"),
                site=it.get("site"),
            )
        except Exception as e:
            print(f"[hunt] tg skip/err: {e}", flush=True)

    if rebuild:
        try:
            import build_ca_finds
            build_ca_finds.write()
            print("[hunt] ca_finds rebuilt", flush=True)
        except Exception as e:
            print(f"[hunt] ca_finds rebuild fail: {e}", flush=True)
    return True


def process_item(st: dict, it: dict) -> dict:
    h = norm_h(it.get("handle"))
    listing = parse_listing(it)
    secs = (listing - now()).total_seconds() if listing else None
    force_recent = secs is not None and 0 <= secs <= T20_MIN * 60

    bag = collect_wallets_for(it)
    wallets = bag["wallets"]
    # Drop addresses that are already token/NFT contracts — don't waste RPC tracing them as EOAs
    filtered = []
    for w in wallets:
        v = classify(w.get("address"), w.get("chain") or it.get("chain"))
        kind = str(v.get("kind") or "").lower()
        if v.get("is_token") or kind in ("token", "nft", "hybrid_404", "hybrid", "contract"):
            # still keep as known for re-verify / creator path
            bag["known_addrs"].append({
                "address": norm_a(w.get("address")),
                "chain": v.get("chain") or w.get("chain"),
                "kind": kind or "contract",
                "is_token": bool(v.get("is_token")),
                "source": w.get("source") or "wallet_list_reclass",
            })
            continue
        filtered.append(w)
    wallets = filtered
    bag["wallets"] = wallets

    persist_wallet_watchlist(it, wallets)

    summary = {
        "handle": it.get("handle"),
        "wallets": len(wallets),
        "known": len(bag["known_addrs"]),
        "site_tokens": len(bag["site_tokens"]),
        "deployed": 0,
        "tokens_emitted": 0,
        "force_recent": force_recent,
    }

    # A) site-scraped tokens
    for t in bag["site_tokens"]:
        v = t.get("verify") or classify(t["address"], t.get("chain"))
        if not (v.get("is_token") or str(v.get("kind") or "").lower() == "token"):
            continue
        # 炼油：跳过 NFT
        if str(v.get("kind") or "").lower() in ("nft", "hybrid_404", "hybrid"):
            continue
        if emit_token(
            st, it,
            ca=t["address"],
            chain=v.get("chain") or t.get("chain"),
            source=t.get("source") or "site",
            conf="medium",
            verify=v,
            rebuild=True,
        ):
            summary["tokens_emitted"] += 1

    # B) re-verify known addrs (may already be tokens, e.g. Fishesrh on robinhood)
    for k in bag["known_addrs"]:
        addr = k.get("address")
        if not addr:
            continue
        v = classify(addr, k.get("chain") or it.get("chain"))
        kind = str(v.get("kind") or "").lower()
        if kind in ("nft", "hybrid_404", "hybrid"):
            continue
        if v.get("is_token") or kind == "token":
            # Only emit if not already alert_ok confirmed with same addr in dedupe;
            # still useful when candidate→first pin for today list
            src = k.get("source") or "known"
            conf = "high" if k.get("ca_status") == "confirmed" else "medium"
            # Prefer not to spam: only emit once per addr (dedupe handles)
            if emit_token(
                st, it,
                ca=addr,
                chain=v.get("chain") or k.get("chain"),
                source=f"reverify:{src}",
                conf=conf,
                verify=v,
                rebuild=False,  # batch rebuild once at end if any
            ):
                summary["tokens_emitted"] += 1

    # C) trace wallets for new CREATE/CREATE2
    deployed = trace_wallets(it, wallets, force_recent=force_recent)
    summary["deployed"] = len(deployed)
    need_rebuild = summary["tokens_emitted"] > 0
    for d in deployed:
        v = classify(d["address"], d.get("chain"))
        kind = str(v.get("kind") or "").lower()
        if kind in ("nft", "hybrid_404", "hybrid", "wallet", "invalid"):
            continue
        if not (v.get("is_token") or kind == "token"):
            continue
        if emit_token(
            st, it,
            ca=d["address"],
            chain=v.get("chain") or d.get("chain"),
            source=d.get("source") or f"wallet_trace:{d.get('wallet')}",
            conf="high" if d.get("tx_hash") else "medium",
            wallet=d.get("wallet"),
            verify=v,
            rebuild=False,
        ):
            summary["tokens_emitted"] += 1
            need_rebuild = True

    if need_rebuild:
        try:
            import build_ca_finds
            build_ca_finds.write()
            print("[hunt] ca_finds rebuilt (batch)", flush=True)
        except Exception as e:
            print(f"[hunt] ca_finds rebuild fail: {e}", flush=True)

    st.setdefault("handles", {})[h] = {
        "at": iso(),
        "wallets": [w.get("address") for w in wallets],
        "wallet_count": len(wallets),
        "deployed": summary["deployed"],
        "tokens_emitted_total": (st.get("handles", {}).get(h) or {}).get("tokens_emitted_total", 0)
        + summary["tokens_emitted"],
        "listing_at": it.get("listing_at"),
    }
    return summary


def cycle_once(st: dict | None = None) -> dict:
    st = st if st is not None else load_state()
    items = today_items()
    interval = pick_interval(items)
    print(
        f"[{iso()}] deployer_hunt cycle handles={len(items)} "
        f"interval={interval}s → {[it.get('handle') for it in items]}",
        flush=True,
    )
    results = []
    for it in items:
        try:
            results.append(process_item(st, it))
        except Exception as e:
            print(f"[hunt] item err @{it.get('handle')}: {e}", flush=True)
            results.append({"handle": it.get("handle"), "error": str(e)[:200]})
    st["last_cycle_at"] = iso()
    st["last_interval_s"] = interval
    st["last_results"] = results
    save_state(st)
    status = {
        "at": iso(),
        "timezone": "Asia/Shanghai",
        "handles": [it.get("handle") for it in items],
        "interval_s": interval,
        "results": results,
    }
    dump_json(STATUS_JSON, status)
    return status


def status_cmd() -> int:
    st = load_state()
    items = today_items()
    interval = pick_interval(items)
    print(json.dumps({
        "at": iso(),
        "timezone": "Asia/Shanghai",
        "handles": [it.get("handle") for it in items],
        "next_interval_s": interval,
        "last_cycle_at": st.get("last_cycle_at"),
        "last_interval_s": st.get("last_interval_s"),
        "handle_state": st.get("handles"),
        "last_results": st.get("last_results"),
    }, ensure_ascii=False, indent=2))
    return 0


def _on_signal(signum, frame):
    global RUNNING
    RUNNING = False
    print(f"[hunt] signal {signum}, stopping…", flush=True)


def watch_loop() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    print(f"[{iso()}] today_deployer_hunt watch start", flush=True)
    while RUNNING:
        t0 = time.time()
        try:
            st = load_state()
            status = cycle_once(st)
            interval = float(status.get("interval_s") or INTERVAL_FAR)
        except Exception as e:
            print(f"[hunt] cycle fail: {e}", flush=True)
            interval = INTERVAL_FAR
        # sleep remaining
        elapsed = time.time() - t0
        wait = max(5.0, interval - elapsed)
        end = time.time() + wait
        while RUNNING and time.time() < end:
            time.sleep(min(5.0, end - time.time()))
    print(f"[{iso()}] today_deployer_hunt stopped", flush=True)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="今日清单部署者猎取 → 代币 CA")
    ap.add_argument("cmd", nargs="?", default="once", choices=("once", "watch", "status"))
    args = ap.parse_args()
    if args.cmd == "status":
        return status_cmd()
    if args.cmd == "watch":
        return watch_loop()
    status = cycle_once()
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
