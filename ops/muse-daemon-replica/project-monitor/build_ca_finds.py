#!/usr/bin/env python3
"""Aggregate every CA we have actually observed into ca_finds.json.

Sources (read-only, never invents addresses):
  - fast_site_alerts.jsonl      NEW_JS_CA (fast poller)
  - js_factory_events.jsonl     NEW_JS_CA (30m batch history)
  - js_factory_scan_latest.json results[].addresses
  - listing_scan_latest.json    results[].cas
  - watchlist.json              locked ca / ca_alt / mint
  - wallet_trace_latest.json    TRACE_CA (wallet→deployed contract) + kind tags
  - wallet_trace_events.jsonl   TRACE_CA history
  - onchain_lock_alerts.jsonl   ONCHAIN_LOCK (wallet/token match on new deploys)
  - solana_lock_alerts.jsonl    ONCHAIN_LOCK from Helius Solana webhooks
  - tapeout_ca_alerts.jsonl     TAPEOUT_CA (watched-creator / official-X only)
  - tapeout_name_match_unconfirmed.jsonl → suspected_copycats[] (疑似山寨·同名非官方, never in finds)
  - tapeout_x_posts.jsonl       official X address registry (official_x provenance)

Confidence model (schema_version 2, ca_confidence.py) adds per row:
  ca_status: confirmed | candidate | superseded | not_ca  (suspected_copycat rows live in suspected_copycats[])
  ca_status_zh, provenance: wallet_factory | official_x | both | null, provenance_zh,
  official_x_confirmed, wallet_factory_confirmed, official_x_url?, ca_role (token|transistors|processor|null),
  alert_ok (true only for confirmed and not 已开盘), superseded_by?, confirm_basis_zh?
  ca_locked, ca_locked_at, locked_by_official_x_url, locked_cas[], project_key
  (set once official X posts a verified CA; later CAs for that project are skipped)

Output schema:
  { "generated_at": ISO, "count": N,
    "finds": [ {project, handle, chain, address, source, evidence_url,
                detected_at, confidence, note, kind?, traced_from?, sources[]} ] }
  kind: "wallet" | "contract" | "unknown" when classified.
  label_zh: 「扫出钱包」 for wallets, 「合约CA」 for contracts.
  Wallet rows are KEPT (not treated as token CA for launch prune); TRACE_CA rows link via traced_from.
P0 (2026-10-24, spec「开盘前精准锁定 CA」):
  - 32/64-hex hashes never enter finds (logged to hex_hash_dropped.jsonl only)
  - sources carrying the same post_url (official X) are recorded once (earliest detected_at)
  - type-aware gate (ca_gate.gate_for_categories): ERC721/1155 → ok, ca_role nft only when the
    project's candidates.json category expects nft (NFT铸造 / GameFi); NFT confirmed only via official X
  - EOAs: watch_promoted=true + watched_wallets.json (handle/chain/wallet/source/confidence/
    evidence_url/added_at/expires_at); still ca_status not_ca, never a CA
  - E1: funding_link / matched_by / creator / creator_watch_source; top-level coverage_stats
  - optional per-row fields: categories, strategy, watch_promoted, lock_time, listing_time
    (= on-chain FIRST EXTERNAL BUY, excludes creation-tx dev buy; launch_config.json),
    first_buy_time (raw any-buy incl. creation-tx), listing_time_estimate (listing_times.json,
    estimate only), lead_seconds (= listing_time - lock_time)
  - top-level: watched_wallet_count, watched_wallets[], strategy_stats, launch_definition,
    hex_hash_dropped_count
Dedupe key: (handle.lower(), address) — EVM addresses compared lowercase,
others (Solana base58) case-sensitive.
Also mirrored to /workspace/push-radar/data/ca_finds.json.
"""
from __future__ import annotations

import fcntl
import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
OUT = BASE / "ca_finds.json"
MIRROR = Path("/workspace/push-radar/data/ca_finds.json")
LOCK = BASE / ".ca_finds.lock"
HEX_LOG = BASE / "hex_hash_dropped.jsonl"
FIRST_BUY_BUDGET_S = 90.0
SH = ZoneInfo("Asia/Shanghai")

LOW_HANDLES = {"baodotla", "ballast"}
LOW_NAMES = {"baola", "ballast"}
LOW_NOTE = "低置信：疑似第三方 feed/图标站嵌入，未必是本项目 CA"
CONF_RANK = {"low": 0, "medium": 1, "high": 2, "confirmed": 3}


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _jsonl(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except Exception:
            continue


def _addr_type(addr: str) -> str:
    return "evm" if addr.lower().startswith("0x") and len(addr) == 42 else "solana"


def _norm(addr: str) -> str:
    return addr.lower() if _addr_type(addr) == "evm" else addr


def _evidence(source: str | None, fallback: str | None = None) -> str | None:
    s = source or ""
    for pre in ("inline:", "html:", "site:", "script:", "js:"):
        if s.startswith(pre):
            return s[len(pre):]
    if s.startswith("http"):
        return s
    return fallback


def _is_low(name: str | None, handle: str | None) -> bool:
    return (handle or "").strip().lower() in LOW_HANDLES or (name or "").strip().lower() in LOW_NAMES


def _sh_now() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def _append_src(cur: dict, entry_src: dict) -> bool:
    """Append a source; a source with a post_url already recorded for the same origin is merged
    (earliest detected_at kept) instead of duplicated. Returns True when appended."""
    pu = entry_src.get("post_url")
    if pu:
        for s0 in cur.setdefault("sources", []):
            if s0.get("post_url") == pu and s0.get("origin") == entry_src.get("origin"):
                d_new, d_old = entry_src.get("detected_at"), s0.get("detected_at")
                if d_new and (not d_old or str(d_new) < str(d_old)):
                    s0["detected_at"] = d_new
                return False
    cur.setdefault("sources", []).append(entry_src)
    return True


def _iso_diff(later: str | None, earlier: str | None):
    try:
        return int((datetime.fromisoformat(later) - datetime.fromisoformat(earlier)).total_seconds())
    except Exception:
        return None


OFFICIAL_ORIGINS = {"x_official", "tapeout_official"}
WALLET_SRC_ORIGINS = {"wallet_trace", "wallet_trace_events", "onchain_lock", "solana_lock", "tapeout_watch",
                      "solana_wallet_mints"}


def _lock_time(f: dict) -> str | None:
    """System's first lock time of a confirmed CA = earliest detected_at among the sources that
    support its provenance (official X post / watched-wallet create)."""
    if f.get("ca_status") != "confirmed":
        return None
    want = set()
    if f.get("official_x_confirmed"):
        want |= OFFICIAL_ORIGINS
    if f.get("wallet_factory_confirmed"):
        want |= WALLET_SRC_ORIGINS
    ts = []
    for s0 in f.get("sources") or []:
        if s0.get("origin") in want or (f.get("official_x_confirmed") and s0.get("official_x")):
            if s0.get("detected_at"):
                ts.append(str(s0["detected_at"]))
    return min(ts) if ts else f.get("detected_at")


def _iso_ts(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, (int, float)):
            return float(v)
        from datetime import datetime
        return datetime.fromisoformat(str(v).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def compute_coverage_stats(rows: list[dict]) -> dict:
    """§9 / §12.2 coverage_stats. listing = first external buy (listing_time).
    Success = confirmed AND lead_seconds > 0 AND address matches final official_x CA
    for that project (else the sole confirmed token CA)."""
    from collections import Counter
    def pk(f):
        h = (f.get("handle") or "").lstrip("@").lower().strip()
        return h or (f.get("project") or "").lower().strip()

    final: dict[str, dict] = {}
    for f in rows:
        if f.get("ca_status") != "confirmed":
            continue
        k = pk(f)
        if not k:
            continue
        if f.get("official_x_confirmed") or f.get("provenance") in ("official_x", "both"):
            final[k] = f
        elif k not in final:
            final[k] = f

    pre_total = 0
    pre_ok = 0
    leads: list[float] = []
    by_line = Counter()
    for f in rows:
        if f.get("ca_status") != "confirmed":
            continue
        lock, listing, lead = f.get("lock_time"), f.get("listing_time"), f.get("lead_seconds")
        if not (lock and listing and lead is not None):
            continue
        pre_total += 1
        if not (isinstance(lead, (int, float)) and lead > 0):
            continue
        k = pk(f)
        fin = final.get(k)
        if not fin or (fin.get("address") or "").lower() != (f.get("address") or "").lower():
            continue
        pre_ok += 1
        leads.append(float(lead))
        mb = f.get("matched_by") or []
        if "funding_link" in mb:
            by_line["funding"] += 1
        elif "creator_wallet" in mb:
            by_line["wallet"] += 1
        elif "launchpad_factory" in mb:
            by_line["factory"] += 1
        else:
            by_line["other"] += 1

    n_final = len(final)
    cov = (pre_ok / n_final) if n_final else 0.0
    prec = (pre_ok / pre_total) if pre_total else 0.0
    med = None
    if leads:
        leads_s = sorted(leads)
        mid = len(leads_s) // 2
        med = leads_s[mid] if len(leads_s) % 2 else (leads_s[mid - 1] + leads_s[mid]) / 2
    return {
        "total_projects_with_final_ca": n_final,
        "prelaunch_locked_correct": pre_ok,
        "prelaunch_locked_total": pre_total,
        "coverage": round(cov, 4),
        "precision": round(prec, 4),
        "median_lead_seconds": med,
        "success_by_line": dict(by_line),
        "listing_definition": "first_external_buy",
    }


def _funding_for_find(f: dict, *, wallet_meta: dict, use_network: bool,
                      cache: dict, budget_left: list) -> dict | None:
    """E1: attach funding_link for a candidate deployer. Mutates nothing on miss.
    budget_left is a 1-element list of remaining seconds (mutable)."""
    creator = (f.get("traced_from") or "").strip()
    chain = f.get("chain")
    if not creator.lower().startswith("0x") or not chain or chain in ("solana", "evm", "unknown", "未知"):
        return f.get("funding_link")
    # Skip if creator is already high-tier watched — H1 covers it; still useful for shared but costly
    key = f"{chain}:{(creator or '').lower()}"
    if key in cache:
        return cache[key]
    if not use_network or budget_left[0] <= 0:
        return None
    try:
        import time as _t
        import funding_links as _fl
        t0 = _t.time()
        # graph = all watched wallets for this handle + global high/medium
        graph = {}
        h = (f.get("handle") or "").lstrip("@").lower()
        for addr, meta in (wallet_meta or {}).items():
            mh = (meta.get("handle") or "").lstrip("@").lower()
            if meta.get("confidence") in ("high", "medium") or mh == h:
                graph[addr] = meta
        res = _fl.analyze_deployer(
            creator, chain,
            deployed_at=f.get("detected_at"),
            graph_wallets=graph,
        )
        link = res.get("funding_link")
        cache[key] = link
        budget_left[0] -= (_t.time() - t0)
        return link
    except Exception:
        return None



def build(*, replay: bool = False, ww_path: Path | None = None, hex_log: Path | None = None,
          first_buy_cache: Path | None = None, first_buy_budget_s: float | None = None,
          funding_budget_s: float | None = None, funding_cache: Path | None = None) -> dict:
    """replay=True: no lock writes / skip-log writes / verify-cache writes (read-only replay)."""
    hex_log = hex_log or HEX_LOG
    hex_dropped: list[dict] = []
    wl = _load(BASE / "watchlist.json", {})
    projects = wl.get("projects") or []
    by_handle = {(p.get("handle") or "").lower(): p for p in projects if p.get("handle")}
    by_name = {(p.get("name") or "").lower(): p for p in projects if p.get("name")}

    finds: dict[tuple[str, str], dict] = {}

    def add(*, name, handle, address, source, detected_at, confidence, chain=None, note=None, origin, snippet=None, kind=None, traced_from=None, evidence_url=None, label_zh=None, src_meta=None):
        if not address or not isinstance(address, str):
            return
        address = address.strip()
        # P0: 32/64-hex strings are hashes, never addresses → log only, never a finds row
        from ca_gate import is_hex_hash
        if is_hex_hash(address):
            hex_dropped.append({"type": "HEX_HASH_DROPPED", "at": _sh_now(), "handle": handle, "name": name,
                                "value": address, "len": len(address.removeprefix("0x")),
                                "origin": origin, "source": source, "detected_at": detected_at})
            return
        # PROJECT CA LOCK: drop later CAs for a locked project (unless address is already
        # in locked_cas, or this is an official-X attach / superseded historical row).
        # Activity is not built here — untouched.
        if origin not in ("tapeout_superseded",) and kind != "wallet":
            try:
                from ca_confidence import should_skip_ca, is_from_official_x, log_locked_skip
                ox = is_from_official_x(source, handle=handle, post_url=(src_meta or {}).get("post_url"))
                if origin == "tapeout_official":
                    ox = ox or bool((src_meta or {}).get("official_x"))
                skip, why = should_skip_ca(handle=handle, name=name, address=address,
                                           source=source, from_official_x=ox,
                                           post_url=(src_meta or {}).get("post_url"))
                if skip:
                    # audit only — do not create a finds row
                    if replay:
                        return
                    log_locked_skip(handle=handle, name=name, address=address, source=source,
                                    reason=why, extra={"origin": origin})
                    return
            except Exception:
                pass
        proj = by_handle.get((handle or "").lower()) or by_name.get((name or "").lower()) or {}
        name = name or proj.get("name")
        handle = handle or proj.get("handle")
        key = ((handle or name or "?").lower(), _norm(address))
        low = _is_low(name, handle)
        if low:
            confidence, note = "low", LOW_NOTE
        if not chain:
            if proj.get("ca") and _norm(proj["ca"]) == _norm(address) and proj.get("ca_chain"):
                chain = proj["ca_chain"]
            else:
                chain = _addr_type(address)
        if _addr_type(address) == "solana" and address.endswith("pump") and address == address.lower():
            extra = "address appears all-lowercase (taken from a URL); Solana is case-sensitive — verify exact mint"
            note = f"{note}; {extra}" if note else extra
        sn = (snippet or "").lower()
        hint = None
        if "ref=" in sn and _norm(address).lower() in sn.split("ref=", 1)[1][:60].lower():
            hint = "来自推荐链接 ?ref= 参数，多半是钱包而非代币 CA"
        elif "tokenicon" in sn or "token-icon" in sn:
            hint = "来自页面代币图标 URL，可能是第三方代币，未必是本项目 CA"
        # carry signal_note_zh from JS enrich when present in snippet meta path
        if hint and hint not in (note or ""):
            note = f"{note}; {hint}" if note else hint
        # wallet-referral note forces kind=wallet unless already contract
        if hint and "wallet" in hint and not kind:
            kind = "wallet"
        ev_url = evidence_url or _evidence(source, proj.get("x_url"))
        cur = finds.get(key)
        entry_src = {"origin": origin, "source": source, "detected_at": detected_at}
        if src_meta:
            entry_src.update({k: v for k, v in src_meta.items() if v not in (None, "", False)})
        if cur is None:
            entry = {
                "project": name,
                "handle": handle,
                "chain": chain,
                "address": address,
                "source": source,
                "evidence_url": ev_url,
                "detected_at": detected_at,
                "confidence": confidence,
                "note": note,
                "sources": [entry_src],
            }
            if kind:
                entry["kind"] = kind
            if not label_zh and kind == "wallet":
                label_zh = "扫出钱包"
            elif not label_zh and kind == "contract":
                label_zh = "合约CA"
            if label_zh:
                entry["label_zh"] = label_zh
            if note and any("一" <= ch <= "鿿" for ch in note):
                entry["note_zh"] = note
            if traced_from:
                entry["traced_from"] = traced_from
            finds[key] = entry
            return
        _append_src(cur, entry_src)
        if detected_at and (not cur["detected_at"] or detected_at < cur["detected_at"]):
            cur["detected_at"] = detected_at
        if not low and CONF_RANK.get(confidence, 0) > CONF_RANK.get(cur["confidence"], 0):
            cur["confidence"] = confidence
            cur["source"], cur["evidence_url"] = source, ev_url or cur["evidence_url"]
        if cur.get("chain") in ("evm", "solana") and chain not in ("evm", "solana"):
            cur["chain"] = chain
        if note and note not in (cur.get("note") or ""):
            cur["note"] = f"{cur['note']}; {note}" if cur.get("note") and LOW_NOTE not in note else note
        # prefer mixed-case checksum form for EVM display
        if address != address.lower() and cur["address"] == cur["address"].lower():
            cur["address"] = address
        # kind: contract wins over wallet; never drop wallet once set unless contract proven
        if kind == "contract":
            cur["kind"] = "contract"
            cur["label_zh"] = label_zh or "合约CA"
        elif kind == "wallet" and cur.get("kind") != "contract":
            cur["kind"] = "wallet"
            cur["label_zh"] = label_zh or "扫出钱包"
        elif label_zh and not cur.get("label_zh"):
            cur["label_zh"] = label_zh
        if traced_from and not cur.get("traced_from"):
            cur["traced_from"] = traced_from
        if evidence_url and (not cur.get("evidence_url") or origin == "wallet_trace"):
            if origin == "wallet_trace" or not cur.get("evidence_url"):
                cur["evidence_url"] = evidence_url

    # 1) fast poller alerts (NEW_JS_CA = contract/unknown; SCANNED_WALLET = EOA; X_CA = official X)
    for ev in _jsonl(BASE / "fast_site_alerts.jsonl"):
        et = ev.get("type")
        if et not in ("NEW_JS_CA", "SCANNED_WALLET", "X_CA"):
            continue
        kind = ev.get("kind") or ("wallet" if et == "SCANNED_WALLET" else None)
        conf = ev.get("confidence")
        if et == "X_CA":
            conf_out = "high"
            src = ev.get("evidence_url") or ev.get("source") or "x_post"
            if ev.get("handle") and not str(src).startswith(("http", "x:")):
                src = f"x:@{str(ev.get('handle')).lstrip('@')}"
            note = ev.get("alert_zh") or ev.get("note") or "官推X扫到并已链上核验"
            add(name=ev.get("name"), handle=ev.get("handle"), address=ev.get("address"),
                source=src, detected_at=ev.get("ts") or ev.get("at"),
                confidence=conf_out, chain=ev.get("chain"),
                note=note, origin="x_official", snippet=ev.get("snippet"),
                kind=kind or "token", label_zh=ev.get("label_zh") or "合约CA",
                evidence_url=ev.get("evidence_url"),
                src_meta={"official_x": True, "post_url": ev.get("evidence_url")})
            continue
        if conf == "low":
            conf_out = "low"
        elif et == "SCANNED_WALLET" or kind == "wallet":
            conf_out = "high"  # classification high; not a token CA
        elif conf in ("high", "confirmed"):
            conf_out = "high"
        elif conf in ("normal", "medium", None):
            conf_out = "medium"
        else:
            conf_out = "medium"
        add(name=ev.get("name"), handle=ev.get("handle"), address=ev.get("address"),
            source=ev.get("source") or f"site:{ev.get('site')}", detected_at=ev.get("at"),
            confidence=conf_out, chain=ev.get("chain"),
            note=ev.get("note"), origin="fast_site_alerts", snippet=ev.get("snippet"),
            kind=kind, label_zh=ev.get("label_zh") or ("扫出钱包" if kind == "wallet" else None))
    # 2) batch JS event history
    for ev in _jsonl(BASE / "js_factory_events.jsonl"):
        if ev.get("type") in ("NEW_JS_CA", "SCANNED_WALLET", "NFT_CONTRACT", "UNVERIFIED_ADDR", "X_CA"):
            kind = ev.get("kind") or ("wallet" if ev.get("type") == "SCANNED_WALLET" else None)
            conf = ev.get("signal_confidence") or "medium"
            if conf not in ("low", "medium", "high"):
                conf = "medium"
            note = ev.get("signal_note_zh") or ev.get("gate_note_zh") or ev.get("gate_note") or ev.get("note")
            add(name=ev.get("name"), handle=ev.get("handle"), address=ev.get("address"),
                source=ev.get("source"), detected_at=ev.get("at"), confidence=conf,
                origin="js_factory_events", snippet=ev.get("snippet"),
                kind=kind, note=note, label_zh=ev.get("label_zh"))
    # 3) latest batch JS scan
    js = _load(BASE / "js_factory_scan_latest.json", {})
    js_at = js.get("checked_at_iso") or js.get("checked_at")
    for r in js.get("results") or []:
        for a in r.get("addresses") or []:
            conf = a.get("signal_confidence") or "medium"
            if conf not in ("low", "medium", "high"):
                conf = "medium"
            note = a.get("signal_note_zh")
            add(name=r.get("name"), handle=r.get("handle"), address=a.get("address"),
                source=a.get("source"), detected_at=js_at, confidence=conf,
                origin="js_factory_scan_latest", snippet=a.get("snippet"), note=note)
    # 4) listing scan CAs (X posts / bios / sites)
    ls = _load(BASE / "listing_scan_latest.json", {})
    ls_at = ls.get("checked_at_iso") or ls.get("checked_at")
    for r in ls.get("results") or []:
        for c in r.get("cas") or []:
            src = c.get("source") or ""
            conf = "high" if "x.com/" in src else "medium"
            add(name=r.get("name"), handle=r.get("handle"), address=c.get("address"),
                source=src, detected_at=r.get("checked_at") or ls_at, confidence=conf,
                origin="listing_scan_latest", snippet=c.get("snippet"))
    # 5) watchlist locked CAs
    for p in projects:
        when = p.get("last_checked") or p.get("locked_at")
        if p.get("ca"):
            src = p.get("ca_source") or "watchlist"
            add(name=p.get("name"), handle=p.get("handle"), address=p["ca"],
                source=src if src.startswith(("site:", "http")) else f"{src}:{p.get('x_url') or ''}".rstrip(":"),
                detected_at=when, confidence="high", chain=p.get("ca_chain"),
                origin="watchlist.ca")
        for w in p.get("scanned_wallets") or []:
            if isinstance(w, str) and w:
                add(name=p.get("name"), handle=p.get("handle"), address=w,
                    source="watchlist.scanned_wallets", detected_at=when, confidence="medium",
                    origin="watchlist.scanned_wallets", kind="wallet", label_zh="扫出钱包")
        for fld in ("ca_alt", "mint"):
            v = p.get(fld)
            vals = v if isinstance(v, list) else [v]
            for x in vals:
                if isinstance(x, str) and x:
                    add(name=p.get("name"), handle=p.get("handle"), address=x,
                        source=f"watchlist.{fld}", detected_at=when, confidence="medium",
                        origin=f"watchlist.{fld}")

    # 6) wallet → CA traces: tag existing finds with kind (never invent new rows from classify)
    wt = _load(BASE / "wallet_trace_latest.json", {})
    by_addr: dict[str, list] = {}
    for key, cur in finds.items():
        by_addr.setdefault(_norm(cur["address"]), []).append(cur)
    for r in wt.get("results") or []:
        clf = r.get("classification") or {}
        kind = clf.get("kind")
        addr = r.get("address")
        if kind not in ("wallet", "contract") or not addr:
            continue
        targets = by_addr.get(_norm(addr)) or []
        # Prefer same handle match; else tag all existing rows with this address
        handle_l = (r.get("handle") or "").lower()
        matched = [c for c in targets if (c.get("handle") or "").lower() == handle_l] or targets
        note = ("classified as EOA/wallet via eth_getCode" if kind == "wallet"
                else f"classified as contract ({clf.get('code_bytes')} bytes)")
        for cur in matched:
            if kind == "contract":
                cur["kind"] = "contract"
                cur["label_zh"] = "合约CA"
            elif cur.get("kind") != "contract":
                cur["kind"] = "wallet"
                cur["label_zh"] = "扫出钱包"
            if clf.get("chain") and cur.get("chain") in ("evm", "solana", None, "", "未知", "unknown"):
                cur["chain"] = clf["chain"]
            elif clf.get("chain") and kind == "contract":
                cur["chain"] = clf["chain"]  # prefer chain where bytecode found
            if note and note not in (cur.get("note") or ""):
                cur["note"] = f"{cur['note']}; {note}" if cur.get("note") else note
            cur.setdefault("sources", []).append({
                "origin": "wallet_trace.classify",
                "source": r.get("source") or "wallet_trace:classify",
                "detected_at": wt.get("generated_at"),
            })
    for tf in wt.get("trace_finds") or []:
        add(
            name=tf.get("project"), handle=tf.get("handle"), address=tf.get("address"),
            source=tf.get("source") or "wallet_trace",
            detected_at=tf.get("detected_at") or wt.get("generated_at"),
            confidence=tf.get("confidence") or "medium",
            chain=tf.get("chain"),
            note=tf.get("note"),
            origin="wallet_trace", kind="contract",
            traced_from=tf.get("wallet"),
            evidence_url=tf.get("evidence_url"),
        )
    # 6b) classification events history (latest may be rebuilt without some rows)
    latest_addrs = {_norm(r.get("address") or "") for r in (wt.get("results") or [])}
    for ev in _jsonl(BASE / "wallet_trace_events.jsonl"):
        if ev.get("type") not in ("WALLET_CLASSIFIED", "ADDR_CLASSIFIED"):
            continue
        a = ev.get("address") or ""
        k = (ev.get("kind") or "").lower()
        if not a or k not in ("wallet", "contract") or _norm(a) in latest_addrs:
            continue
        hl = (ev.get("handle") or "").lower()
        for cur in by_addr.get(_norm(a)) or []:
            if hl and (cur.get("handle") or "").lower() != hl:
                continue
            if k == "contract":
                cur["kind"], cur["label_zh"] = "contract", "合约CA"
            elif cur.get("kind") != "contract":
                cur["kind"], cur["label_zh"] = "wallet", "扫出钱包"
            if ev.get("chain") and ev["chain"] not in ("evm",) and cur.get("chain") in ("evm", None, ""):
                cur["chain"] = ev["chain"]
            n = ev.get("note") or ("classified as EOA/wallet via eth_getCode" if k == "wallet" else None)
            if n and n not in (cur.get("note") or ""):
                cur["note"] = f"{cur['note']}; {n}" if cur.get("note") else n
    # 7) TRACE_CA event history (in case latest was rebuilt without a hit)
    for ev in _jsonl(BASE / "wallet_trace_events.jsonl"):
        if ev.get("type") != "TRACE_CA":
            continue
        via = ev.get("via") or "?"
        note = ev.get("note_zh") or ev.get("note") or f"traced from wallet {ev.get('wallet')} via {via}"
        if via == "create2_derive" and "CREATE2" not in note:
            note = f"CREATE2推导 via={via}; {note}"
        add(
            name=ev.get("project"), handle=ev.get("handle"), address=ev.get("address"),
            source=f"wallet_trace:{ev.get('wallet')}",
            detected_at=ev.get("at"),
            confidence="high" if ev.get("tx_hash") else "medium",
            chain=ev.get("chain"),
            note=note,
            origin="wallet_trace_events", kind="contract",
            traced_from=ev.get("wallet"),
            evidence_url=ev.get("evidence_url"),
            src_meta={"via": via, "factory_id": ev.get("factory_id")},
        )

    # 8) on-chain lock alerts (wallet deployer and/or ERC20 name/symbol match)
    for ev in _jsonl(BASE / "onchain_lock_alerts.jsonl"):
        if ev.get("type") != "ONCHAIN_LOCK":
            continue
        if ev.get("synthetic"):
            continue
        conf = ev.get("confidence") or "medium"
        if conf not in ("low", "medium", "high", "confirmed"):
            conf = "medium"
        # map confirmed -> high for ca_finds schema (CONF_RANK has no confirmed)
        conf_out = "high" if conf == "confirmed" else conf
        note = (
            f"onchain_lock {conf} via {ev.get('reason') or ev.get('via')}; "
            f"deployer={ev.get('deployer')}; "
            f"token={ev.get('token_symbol') or ''} / {ev.get('token_name') or ''}"
        ).strip()
        add(
            name=ev.get("project"), handle=ev.get("handle"), address=ev.get("address"),
            source="onchain_lock",
            detected_at=ev.get("at"),
            confidence=conf_out,
            chain=ev.get("chain"),
            note=note,
            origin="onchain_lock",
            kind="contract",
            traced_from=ev.get("deployer"),
            evidence_url=None,
            src_meta={"reason": ev.get("reason") or ev.get("via"), "via": ev.get("via")},
        )


    # 8b) TapeRobot/TapeOut watch (tapeout_push.py) — verified token / ERC-1155 transistors / processor
    # CONFIDENCE MODEL (ca_confidence.py, 2026-10-21): confirmed only via watched-wallet factory create
    # (wallet_factory) and/or official X post (official_x). Name-only creates -> suspected_copycats
    # (疑似山寨·同名非官方), never in finds. Watched-wallet creates that official X contradicted -> superseded.
    tcfg = _load(BASE / "tapeout_watch_wallets.json", {})
    official = {(o.get("address") or "").lower(): o for o in (tcfg.get("official") or []) if o.get("address")}
    superseded_cfg = {(o.get("address") or "").lower(): o for o in (tcfg.get("superseded") or []) if o.get("address")}
    copy_set = {(c.get("address") or "").lower() for c in (tcfg.get("copycats") or []) if c.get("address")}
    watched_wallets = {(w.get("address") or "").lower() for w in (tcfg.get("wallets") or []) if w.get("address")}
    # P1: merge watched_wallets.json + wallet_watchlist.json confidence map for assess/provenance
    try:
        import watched_wallets as _ww_mod
        wallet_meta = _ww_mod.meta_from_watchlists(ww_path=(ww_path or _ww_mod.STORE))
        for a, meta in wallet_meta.items():
            if meta.get("confidence") == "high":
                watched_wallets.add(a)
    except Exception:
        wallet_meta = {}
    # official X address registry: config + every address the official account itself posted
    official_x: dict[str, dict] = {a: {"post_url": o.get("post_url"), "handle": "TapeRobot_bsc"}
                                   for a, o in official.items() if o.get("official_x")}
    for ev in _jsonl(BASE / "tapeout_x_posts.jsonl"):
        for a in ev.get("addresses") or []:
            official_x.setdefault(a.lower(), {"post_url": f"https://x.com/TapeRobot_bsc/status/{ev.get('id')}",
                                              "handle": "TapeRobot_bsc"})
    copycats: dict[str, dict] = {}

    def _copycat(ev, why):
        a = (ev.get("address") or "").lower()
        if not a or a in copycats or a in official_x or a in official:
            return
        copycats[a] = {
            "project": "【疑似山寨·同名非官方】" + (ev.get("token_name") or ev.get("name") or "TapeRobot"),
            "handle": "TapeOutWatch", "chain": "bsc", "address": ev.get("address"),
            "kind": ev.get("ca_kind") or ev.get("role_hint"), "label_zh": "疑似山寨·同名非官方",
            "official": False, "suspected_copycat": True, "status": "name_match_unconfirmed",
            "ca_status": "suspected_copycat", "ca_status_zh": "疑似山寨", "provenance": None,
            "official_x_confirmed": False, "wallet_factory_confirmed": False, "alert_ok": False,
            "ca_role": ev.get("ca_kind") or ev.get("role_hint"),
            "creator": ev.get("creator"), "creator_watched": False, "tx": ev.get("tx"), "detected_at": ev.get("at"),
            "processor": ev.get("processor"), "transistors": ev.get("transistors"),
            "evidence_url": f"https://bscscan.com/tx/{ev['tx']}" if ev.get("tx") else None,
            "note": f"同名非官方：创建者 {ev.get('creator')} 不在监控钱包内，官推未确认；{why}",
        }

    for ev in _jsonl(BASE / "tapeout_name_match_unconfirmed.jsonl"):
        _copycat(ev, "name_match_unconfirmed")
    x_confirm_events = []
    for ev in _jsonl(BASE / "tapeout_ca_alerts.jsonl"):
        if ev.get("type") == "TAPEOUT_X_CONFIRM":
            x_confirm_events.append(ev)
            if ev.get("post_url"):
                official_x.setdefault((ev.get("address") or "").lower(), {"post_url": ev.get("post_url")})
            continue
        if ev.get("type") == "TAPEOUT_NAME_MATCH_UNCONFIRMED" or ev.get("suspected_copycat"):
            _copycat(ev, "retro-marked copycat")
            continue
        if ev.get("type") != "TAPEOUT_CA":
            continue
        a_l = (ev.get("address") or "").lower()
        src_s = str(ev.get("source") or "")
        is_x = src_s.startswith("x:")
        watched = bool(ev.get("creator_watched")) or (ev.get("creator") or "").lower() in watched_wallets \
            or src_s == "wallet:create"
        if a_l in copy_set or (not watched and not is_x and a_l not in official and a_l not in official_x):
            _copycat(ev, "name-only match")
            continue
        add(
            name=ev.get("project"), handle=ev.get("handle"), address=ev.get("address"),
            source=ev.get("source") or "tapeout_watch",
            detected_at=ev.get("at"), confidence="high", chain="bsc",
            note=(f"【{ev.get('label_zh')}】TapeOut监控 {ev.get('token_name') or ''} via {ev.get('source')}; "
                  f"creator={ev.get('creator') or ''}; tx={ev.get('tx') or ''}").strip(),
            origin="tapeout_watch", kind="contract", label_zh=ev.get("label_zh"),
            traced_from=ev.get("creator"),
            evidence_url=(f"https://bscscan.com/tx/{ev['tx']}" if ev.get("tx") else ev.get("post_url") or ev.get("bscscan")),
            src_meta={"creator_watched": watched, "post_url": ev.get("post_url"), "ca_kind": ev.get("ca_kind")},
        )
    # official-X confirmations of an already-pushed address → extra source on the same row
    _rows_by_addr = {}
    for _f in finds.values():
        _rows_by_addr.setdefault(_norm(_f["address"]), []).append(_f)
    for ev in x_confirm_events:
        for cur in _rows_by_addr.get(_norm(ev.get("address") or ""), []):
            _append_src(cur, {"origin": "tapeout_watch", "source": ev.get("source") or "x:@TapeRobot_bsc",
                              "detected_at": ev.get("at"), "post_url": ev.get("post_url")})

    # 8c) Official TapeRobot contracts (official X + watched-creator verified). Only add a row when the
    # address is not already present (avoid duplicate rows across handles); rows get tagged below.
    present = {_norm(f["address"]) for f in finds.values()}
    for a_l, o in official.items():
        if a_l in present:
            continue
        lab = o.get("label_zh") or "官方TapeRobot"
        add(name="TapeRobot", handle="TapeRobot_bsc", address=o["address"],
            source="tapeout:official", detected_at=o.get("created_at"), confidence="high", chain="bsc",
            note=f"【{lab}】官方 TapeRobot；creator={o.get('creator')}; tx={o.get('tx')}; {o.get('verified') or ''}",
            origin="tapeout_official", kind="contract", label_zh=lab, traced_from=o.get("creator"),
            evidence_url=o.get("post_url") or (f"https://bscscan.com/tx/{o['tx']}" if o.get("tx") else None),
            src_meta={"official_x": bool(o.get("official_x")), "wallet_factory": bool(o.get("wallet_factory")),
                      "post_url": o.get("post_url")})
    # 8d) Superseded: watched-wallet creates that official X did NOT confirm (official named another pair)
    for a_l, o in superseded_cfg.items():
        if a_l in present:
            continue
        add(name="TapeRobot", handle="TapeRobot_bsc", address=o["address"],
            source="tapeout:superseded", detected_at=o.get("created_at"), confidence="low", chain="bsc",
            note=f"【{o.get('label_zh')}】{o.get('note') or ''}; superseded_by={o.get('superseded_by')}",
            origin="tapeout_superseded", kind="contract", label_zh=o.get("label_zh"), traced_from=o.get("creator"),
            evidence_url=(f"https://bscscan.com/tx/{o['tx']}" if o.get("tx") else None),
            src_meta={"wallet_factory": True})

    # 9a) Solana wallet→mint heuristic (solana_wallet_mints.py) — still gated later by ca_gate if present
    for ev in _jsonl(BASE / "solana_lock_alerts.jsonl"):
        if ev.get("type") != "SOLANA_TRACE_CA":
            continue
        add(
            name=ev.get("name") or ev.get("project"), handle=ev.get("handle"),
            address=ev.get("address"),
            source=ev.get("source") or "solana_wallet_mints",
            detected_at=ev.get("ts") or ev.get("at"),
            confidence="medium",
            chain="solana",
            note=ev.get("note") or f"SOLANA_TRACE_CA from wallet {ev.get('traced_from')}",
            origin="solana_wallet_mints", kind="contract",
            traced_from=ev.get("traced_from"),
            evidence_url=ev.get("evidence_url"),
            src_meta={"via": "solana_wallet_mints"},
        )

    # 9) Solana Helius lock alerts (also dual-written to onchain_lock_alerts; re-read is idempotent via dedupe)
    for ev in _jsonl(BASE / "solana_lock_alerts.jsonl"):
        if ev.get("type") != "ONCHAIN_LOCK":
            continue
        if ev.get("synthetic"):
            continue
        conf = ev.get("confidence") or "medium"
        if conf not in ("low", "medium", "high", "confirmed"):
            conf = "medium"
        conf_out = "high" if conf == "confirmed" else conf
        note = (
            f"helius_solana {conf} via {ev.get('reason') or ev.get('via')}; "
            f"program={ev.get('program_id') or ev.get('factory')}; "
            f"token={ev.get('token_symbol') or ''} / {ev.get('token_name') or ''}"
        ).strip()
        add(
            name=ev.get("project"), handle=ev.get("handle"), address=ev.get("address"),
            source="helius_solana",
            detected_at=ev.get("at"),
            confidence=conf_out,
            chain=ev.get("chain") or "solana",
            note=note,
            origin="solana_lock",
            kind="contract",
            traced_from=ev.get("deployer"),
            src_meta={"reason": ev.get("reason") or ev.get("via"), "via": ev.get("via")},
            evidence_url=f"https://solscan.io/tx/{ev['tx']}" if ev.get("tx") else None,
        )

    out = sorted(finds.values(), key=lambda f: (f.get("detected_at") or ""), reverse=True)
    # copycat addresses never appear as finds, whatever source picked them up
    _cc = set(copycats) | copy_set
    out = [f for f in out if (f.get("address") or "").lower() not in _cc]
    # Launched/pruned projects (removed_launched.json blocklist): history, never a new CA alert
    rem = _load(BASE / "removed_launched.json", {})
    rem_items = rem.get("items", []) if isinstance(rem, dict) else (rem or [])
    from ca_confidence import provenance as _prov, assess as _assess, project_key as _project_key
    wallet_meta = wallet_meta if "wallet_meta" in locals() else {}
    # Expand blocklist with project aliases (TapeOutWatch ↔ TapeRobot_bsc) so launched
    # projects never stay in active finds / alert_ok under a watch-handle alias.
    blocked_handles = {(e.get("handle") or "").lstrip("@").lower() for e in rem_items if not e.get("restored")}
    blocked_keys = set()
    for h in blocked_handles:
        k = _project_key(h)
        if k:
            blocked_keys.add(k)
    def _is_launched(handle, name=None) -> bool:
        h = (handle or "").lstrip("@").lower()
        if h in blocked_handles:
            return True
        k = _project_key(h, name)
        return bool(k and k in blocked_keys)
    blocked = blocked_handles  # keep name for any legacy readers below
    TAPE_ORIGINS = ("tapeout_watch", "tapeout_official", "tapeout_superseded")
    # HARD CA GATE: every row is verified on-chain; only ERC20 / SPL mint keeps 合约CA.
    from ca_gate import verify_address, gate_for_categories
    import ca_gate as _ca_gate
    if replay:
        _ca_gate._save_cache = lambda c: None  # read-only replay
    from strategies import load_project_categories, primary_strategy, norm_handle
    cats_by_handle = load_project_categories()
    # E1 funding budget / cache (network optional; replay may set funding_budget_s=0)
    _fund_budget = [float(0 if funding_budget_s is None and replay else (funding_budget_s if funding_budget_s is not None else 60.0))]
    _fund_cache: dict = {}
    if funding_cache:
        try:
            _fund_cache = json.loads(Path(funding_cache).read_text(encoding="utf-8"))
        except Exception:
            _fund_cache = {}
    for f in out:
        chain_hint = f.get("chain") if f.get("chain") not in ("evm", "solana", "未知", "unknown", None, "") else None
        v = verify_address(f.get("address") or "", chain_hint)
        k = v.get("kind") or "unknown"
        if k == "unknown" and (f.get("kind") or "").lower() == "wallet":
            k = "wallet"  # earlier eth_getCode wallet proof stands when rpc flaked
        f["kind"] = "contract" if k == "token" else k
        f["addr_kind"] = f["kind"]
        f["is_token"] = bool(v.get("is_token"))
        f["label_zh"] = {"token": "合约CA", "nft": "NFT合约", "hybrid_404": "混合404合约",
                         "contract": "合约(非代币)", "wallet": "扫出钱包",
                         "invalid": "非地址"}.get(k, "未确认地址")
        if k == "nft":
            f["note_zh"] = "NFT合约（非代币），不作为CA"
        elif k == "hybrid_404":
            f["note_zh"] = "混合404/DN404（兼具 ERC20+NFT），不作为纯代币 CA"
            f["is_token"] = False
        f["verify"] = {kk: v.get(kk) for kk in ("kind", "chain", "symbol", "name", "decimals", "code_bytes", "note",
                                               "implementation", "proxy_type") if v.get(kk) is not None}
        if v.get("chain") and v["chain"] not in ("evm", "unknown", "未知"):
            f["chain"] = v["chain"]
        _tape = any((x.get("origin") in TAPE_ORIGINS) for x in (f.get("sources") or []))
        a_l = (f.get("address") or "").lower()
        _off = official.get(a_l)
        _sup = superseded_cfg.get(a_l)
        is_1155 = "1155" in (v.get("note") or "")
        cats = cats_by_handle.get(norm_handle(f.get("handle"))) or ["其他"]
        f["categories"] = cats
        f["strategy"] = primary_strategy(cats)
        gate = gate_for_categories(v if k != "wallet" else dict(v, kind="wallet"), cats, tapeout=_tape)
        # ca_role: what the address is as a launch CA
        if f["is_token"]:
            role = "token"
        elif k == "nft" and _tape:
            role = "transistors" if is_1155 else "processor"
        elif gate.get("ok") and gate.get("role") == "nft":
            role = "nft"  # P0: project NFT contract for NFT铸造 / GameFi only
        else:
            role = None
        verified_ok = role is not None  # wallet / non-expected NFT / non-token contract never a CA
        f["watch_promoted"] = bool(gate.get("promote_to_watch")) and not _is_launched(f.get("handle"), f.get("project"))
        if role == "nft":
            f["confidence"] = "medium" if f.get("confidence") in ("high", "confirmed", "medium") else "low"
        elif not f["is_token"] and not (k == "nft" and _tape) and (k != "wallet" or f.get("confidence") in ("high", "confirmed")):
            # a non-token can never be a high-confidence CA (prevents 已开盘/alert paths)
            f["confidence"] = "medium" if k == "wallet" else "low"
        launched = _is_launched(f.get("handle"), f.get("project"))
        prov = _prov(f, official_x=official_x, watched_wallets=watched_wallets,
                     wallet_meta=wallet_meta)
        if _off:
            prov["official_x"] = prov["official_x"] or bool(_off.get("official_x"))
            prov["wallet_factory"] = prov["wallet_factory"] or bool(_off.get("wallet_factory"))
            prov["x_url"] = prov.get("x_url") or _off.get("post_url")
            prov["name_only"] = False
        # E1 funding link (best-effort; never invent)
        fl = _funding_for_find(f, wallet_meta=wallet_meta,
                               use_network=_fund_budget[0] > 0,
                               cache=_fund_cache, budget_left=_fund_budget)
        if fl:
            f["funding_link"] = fl
        f.update(_assess(f, verified_ok=verified_ok, ca_role=role, prov=prov,
                         superseded_by=(_sup or {}).get("superseded_by"), launched=launched,
                         wallet_meta=wallet_meta, watched_wallets=watched_wallets,
                         funding_link=fl, sibling_same_name=f.get("_siblings_same_name"),
                         expected_window=f.get("expected_window")))
        from ca_confidence import lock_fields as _lock_fields, record_lock as _record_lock
        f.update(_lock_fields(f.get("handle"), f.get("project")))
        # Belt-and-suspenders: confirmed via official_x → ensure project is locked
        if not replay and f.get("ca_status") == "confirmed" and f.get("official_x_confirmed") and f.get("official_x_url"):
            try:
                _record_lock(handle=f.get("handle"), name=f.get("project"), address=f.get("address"),
                             ca_role=f.get("ca_role"), post_url=f.get("official_x_url"),
                             verified=f.get("verify"))
                f.update(_lock_fields(f.get("handle"), f.get("project")))
            except Exception:
                pass
        if _off and f["ca_status"] == "confirmed":
            f["is_token"] = role == "token"
            f["confidence"] = "high"
            f["official"] = True
            f["label_zh"] = _off.get("label_zh") or "官方TapeRobot"
            f["tapeout_ca"] = role in ("transistors", "processor")
            if _off.get("pair_of"):
                f["paired_with"] = _off["pair_of"]  # same factory create tx as the X-confirmed transistors
            for kk in ("mint_price_bnb", "supply_cap", "cpu", "processor"):
                if _off.get(kk) is not None:
                    f.setdefault(kk, _off[kk])
            tag = f"【{f['label_zh']}】"
            if not (f.get("project") or "").startswith(tag):
                f["project"] = tag + (f.get("project") or "TapeRobot").split("】")[-1]
        elif f["ca_status"] == "superseded":
            f["is_token"] = False
            f["confidence"] = "low"
            f["official"] = False
            f["tapeout_ca"] = False
            f["label_zh"] = (_sup or {}).get("label_zh") or "非正式·官推未认"
            tag = f"【{f['label_zh']}】"
            if not (f.get("project") or "").startswith(tag):
                f["project"] = tag + (f.get("project") or "TapeRobot").split("】")[-1]
        elif role == "nft":
            # P0: project mint contract of an NFT铸造 / GameFi project — a valid result, not 非CA
            f["is_token"] = False
            f["note_zh"] = gate.get("note_zh")
        elif _tape and k == "nft":
            # TapeOut transistors (ERC-1155) / processor are the CA users mint — keep visible, no 非CA tag
            f["is_token"] = False
            f["confidence"] = "high" if f["ca_status"] == "confirmed" else "low"
            f["label_zh"] = ("晶体管合约(ERC-1155)" if is_1155 else "TapeOut Processor")
            f["tapeout_ca"] = f["ca_status"] == "confirmed"
        elif not f["is_token"]:
            if k == "wallet" and f.get("watch_promoted"):
                f["note_zh"] = gate.get("note_zh")
            # site CA page renders project/note only (not kind/label) → make the label visible there
            tag = f"【{f['label_zh']}·非CA】"
            proj = (f.get("project") or f.get("handle") or "").split("】")[-1]
            f["project"] = tag + proj
            if not (f.get("note") or "").startswith(tag):
                f["note"] = tag + " " + (f.get("note") or "")
        if f["ca_status"] == "confirmed" and (f.get("provenance") or f.get("matched_by")):
            parts = []
            if f.get("provenance_zh"):
                parts.append(f["provenance_zh"] + (f"（创建者 {prov.get('creator')}）" if prov.get("wallet_factory") and prov.get("creator") else ""))
            fl = f.get("funding_link")
            if fl and not fl.get("excluded_reason"):
                try:
                    from funding_links import basis_zh as _fl_basis
                    bz = _fl_basis(fl)
                except Exception:
                    bz = None
                if bz:
                    parts.append(bz)
            if role == "nft":
                parts.append("项目 NFT 铸造合约（ca_role: nft）")
            if f.get("official_x_confirmed") and not f.get("wallet_factory_confirmed"):
                parts.append("官推事后验证，不计开盘前提前量")
            evs = [e for e in (f.get("evidence") or []) if e.get("kind") != "funding_link"]
            if evs and not f.get("official_x_confirmed"):
                parts.append("硬证据：" + "、".join(e.get("note_zh") or e.get("kind") for e in evs))
            if f.get("veto_note_zh") and f.get("official_x_confirmed"):
                pass  # 事后验证不被否决项挡住
            f["confirm_basis_zh"] = "；".join(p for p in parts if p)
        elif f.get("ca_status") == "candidate" and (f.get("hard_evidence_count") or 0) == 1:
            evs = f.get("evidence") or []
            f["confirm_basis_zh"] = "仅 1 条硬证据，待补齐至 2 条：" + (
                "、".join(e.get("note_zh") or e.get("kind") for e in evs) if evs else "（未知）")
        gate_note = f"ca_gate: {v.get('note')}"
        if v.get("note") and gate_note not in (f.get("note") or ""):
            f["note"] = f"{f['note']}; {gate_note}" if f.get("note") else gate_note
    # P1: conflicting CAs for the same project → mark + demote non-X confirmed
    from ca_confidence import mark_conflicts as _mark_conflicts
    _mark_conflicts(out)

    # E1 post-pass: multi same-name veto once verify.symbol is known
    from collections import defaultdict as _dd
    from ca_confidence import collect_vetoes as _vetoes, STATUS_LABEL as _SL
    _by_sym: dict[str, list] = _dd(list)
    for _f0 in out:
        sym = ((_f0.get("verify") or {}).get("symbol") or "").strip().upper()
        if sym:
            _by_sym[sym].append(_f0)
    for sym, group in _by_sym.items():
        if len(group) < 2:
            continue
        for _f0 in group:
            others = [x for x in group if (x.get("address") or "").lower() != (_f0.get("address") or "").lower()]
            vs = _vetoes(_f0, {
                "wallet_factory": _f0.get("wallet_factory_confirmed"),
                "soft_wallet": _f0.get("soft_wallet"),
                "creator": _f0.get("creator") or _f0.get("traced_from"),
                "name_only": "name_match" in (_f0.get("matched_by") or []),
                "official_x": _f0.get("official_x_confirmed"),
            }, funding_link=_f0.get("funding_link"), sibling_same_name=others)
            if not vs:
                continue
            _f0["vetoes"] = vs
            _f0["veto_note_zh"] = "；".join(v.get("note_zh") or v.get("kind") for v in vs)
            if _f0.get("ca_status") == "confirmed" and not _f0.get("official_x_confirmed"):
                _f0["ca_status"] = "candidate"
                _f0["ca_status_zh"] = _SL["candidate"]
                _f0["alert_ok"] = False


    # Generic name/symbol-only matches (any project, e.g. onchain_lock name match with an unwatched
    # deployer and no official X) are 疑似山寨 too: moved out of active finds, never alert.
    generic_cc = []
    keep = []
    for f in out:
        launched = _is_launched(f.get("handle"), f.get("project"))
        if f.get("ca_status") == "suspected_copycat" and not launched:
            generic_cc.append(dict(f, suspected_copycat=True, official=False, alert_ok=False,
                                   label_zh="疑似山寨·同名未确认", status="name_match_unconfirmed",
                                   creator=f.get("traced_from"), creator_watched=False,
                                   project="【疑似山寨·同名未确认】" + (f.get("project") or "").split("】")[-1]))
        else:
            keep.append(f)
    out = keep
    active = [f for f in out if not _is_launched(f.get("handle"), f.get("project"))]
    history = [f for f in out if _is_launched(f.get("handle"), f.get("project"))]
    all_cc = sorted(list(copycats.values()) + generic_cc, key=lambda c: c.get("detected_at") or "", reverse=True)

    # ---- P0: timing fields (开盘 = first EXTERNAL buy, launch_config.json) ----
    import time as _time
    from first_buy import derive_first_buy, CACHE as _FB_CACHE
    lt_doc = _load(BASE / "listing_times.json", {})
    est_by_handle = {norm_handle(i.get("handle")): i for i in (lt_doc.get("items") or []) if i.get("handle")}
    budget = FIRST_BUY_BUDGET_S if first_buy_budget_s is None else first_buy_budget_s
    t0 = _time.time()
    for f in active + history:
        f["lock_time"] = _lock_time(f)
        est = est_by_handle.get(norm_handle(f.get("handle"))) or {}
        f["listing_time_estimate"] = est.get("listing_at")
        if est.get("listing_at"):
            f["listing_time_estimate_source"] = "listing_times.json"
            f["listing_time_estimate_note_zh"] = "预告开盘时间（仅估计，不是链上首笔外部买入，不参与提前量计算）"
        fb = {"first_buy_time": None, "reason": "not a token"}
        if f.get("is_token") and str(f.get("address") or "").lower().startswith("0x"):
            online = (_time.time() - t0) < budget
            fb = derive_first_buy(f["address"], f.get("chain"), cache_path=first_buy_cache or _FB_CACHE,
                                  use_network=online, hint_time=f.get("detected_at"))
        elif f.get("is_token"):
            online = (_time.time() - t0) < budget
            fb = derive_first_buy(f["address"], f.get("chain") or "solana",
                                  cache_path=first_buy_cache or _FB_CACHE,
                                  use_network=online, hint_time=f.get("detected_at"))
        # raw any-buy (may be creation-tx / same-tx dev buy)
        f["first_buy_time"] = fb.get("first_buy_time")
        f["first_buy_in_creation_tx"] = bool(fb.get("first_buy_in_creation_tx"))
        if fb.get("first_buy_tx"):
            f["first_buy_tx"] = fb.get("first_buy_tx")
        if fb.get("first_external_buy_time"):
            f["first_external_buy_time"] = fb.get("first_external_buy_time")
            f["first_external_buy_tx"] = fb.get("first_external_buy_tx")
        # listing_time / 开盘 = first EXTERNAL buy only
        f["listing_time"] = fb.get("first_external_buy_time")
        if f["listing_time"]:
            f["listing_time_source"] = "first_external_buy_onchain"
            note = "链上第一笔外部买入（不含创建交易里的开发者买入）"
            if f.get("first_buy_in_creation_tx") and f.get("first_buy_time"):
                note += "；创建交易内另有开发者买入已排除"
            if not fb.get("holder_known"):
                note += "；判定为启发式（买入来自未登记的合约池子）"
            f["listing_time_basis_zh"] = note
        else:
            if f.get("is_token") and f.get("first_buy_in_creation_tx") and f.get("first_buy_time"):
                f["listing_time_basis_zh"] = "仅有创建交易内买入（开发者），尚无外部买入，开盘时间暂无法推出"
            elif f.get("is_token"):
                f["listing_time_basis_zh"] = "链上第一笔外部买入时间暂无法推出"
            else:
                f["listing_time_basis_zh"] = None
        f["lead_seconds"] = _iso_diff(f["listing_time"], f["lock_time"]) if f["listing_time"] and f["lock_time"] else None

    # ---- P0: watched_wallets (EOAs promoted, not dropped) ----
    import watched_wallets as _ww
    new_rows = []
    for f in active:
        if not f.get("watch_promoted"):
            continue
        origins = [s0.get("origin") or "" for s0 in f.get("sources") or []]
        srcs = [str(s0.get("source") or "") for s0 in f.get("sources") or []]
        src, conf = _ww.classify_source(origins, srcs)
        est = est_by_handle.get(norm_handle(f.get("handle"))) or {}
        new_rows.append(_ww.make_row(handle=f.get("handle"), chain=f.get("chain"), wallet=f.get("address"),
                                     source=src, confidence=conf, evidence_url=f.get("evidence_url"),
                                     added_at=f.get("detected_at") or _sh_now(), listing_at=est.get("listing_at")))
    ww_doc = _ww.save(new_rows, ww_path or _ww.STORE)
    ww_rows = ww_doc.get("wallets") or []

    if hex_dropped:
        try:
            with hex_log.open("a", encoding="utf-8") as hf:
                for ev in hex_dropped:
                    hf.write(json.dumps(ev, ensure_ascii=False) + "\n")
        except Exception:
            pass

    strategy_stats: dict[str, dict] = {}
    seen_proj: dict[str, set] = {}
    for f in active:
        st = f.get("strategy") or "其他"
        d = strategy_stats.setdefault(st, {"projects": 0, "confirmed": 0, "candidate": 0})
        seen_proj.setdefault(st, set()).add(norm_handle(f.get("handle")) or f.get("project"))
        if f.get("ca_status") in ("confirmed", "candidate"):
            d[f["ca_status"]] += 1
    for st, hs in seen_proj.items():
        strategy_stats[st]["projects"] = len(hs)
    _launch_cfg = _load(BASE / "launch_config.json", {})
    if funding_cache is not None:
        try:
            Path(funding_cache).write_text(json.dumps(_fund_cache, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        except Exception:
            pass
    coverage_stats = compute_coverage_stats(active + history)
    try:
        from funding_links import gaps as _fl_gaps
        _funding_gaps_list = _fl_gaps()
    except Exception:
        _funding_gaps_list = []

    return {
        "generated_at": datetime.now(SH).isoformat(timespec="seconds"),
        "schema_version": 2,
        "confidence_model": "ca_confidence.py: confirmed = verified(token|TapeOut transistors/processor) AND "
                            "provenance wallet_factory|official_x|both; name-only = suspected_copycat (疑似山寨); "
                            "watched-wallet create contradicted by official X = superseded; site scrape only = candidate",
        "count": len(active),
        "token_ca_count": sum(1 for f in active if f.get("is_token")),
        "wallet_count": sum(1 for f in active if f.get("kind") == "wallet"),
        "confirmed_count": sum(1 for f in active if f.get("ca_status") == "confirmed"),
        "candidate_count": sum(1 for f in active if f.get("ca_status") == "candidate"),
        "status_counts": {st: sum(1 for f in active if f.get("ca_status") == st)
                          for st in ("confirmed", "candidate", "superseded", "not_ca")},
        "finds": active,
        "launched_history_count": len(history),
        "launched_history": history,
        "suspected_copycat_count": len(all_cc),
        "suspected_copycats": all_cc,
        "ca_locked_project_count": len({f.get("project_key") for f in active + history if f.get("ca_locked")}),
        "ca_locked_projects": sorted({f.get("project_key") for f in active + history if f.get("ca_locked") and f.get("project_key")}),
        "watched_wallet_count": len(ww_rows),
        "watched_wallets": [{k2: r.get(k2) for k2 in ("handle", "chain", "wallet", "source", "confidence",
                                                     "evidence_url", "added_at", "expires_at")} for r in ww_rows],
        "strategy_stats": strategy_stats,
        "launch_definition": _launch_cfg.get("launch_definition") or "first_external_buy",
        "launch_definition_zh": _launch_cfg.get("launch_definition_zh"),
        "hex_hash_dropped_count": len({(e.get("handle"), e.get("value")) for e in hex_dropped}),
        "coverage_stats": coverage_stats,
        "funding_gaps": _funding_gaps_list,
    }


def write() -> dict:
    LOCK.touch(exist_ok=True)
    with LOCK.open("r+") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        doc = build()
        tmp = OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp.replace(OUT)
        try:
            MIRROR.parent.mkdir(parents=True, exist_ok=True)
            mtmp = MIRROR.with_suffix(".tmp")
            shutil.copyfile(OUT, mtmp)
            mtmp.replace(MIRROR)
        except Exception as e:  # mirror is best-effort
            print(f"ca_finds mirror failed: {e}")
        fcntl.flock(lf, fcntl.LOCK_UN)
    return doc


if __name__ == "__main__":
    d = write()
    print(f"ca_finds.json: {d['count']} finds -> {OUT} (+ {MIRROR})")
