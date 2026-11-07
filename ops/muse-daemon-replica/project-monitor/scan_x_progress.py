#!/usr/bin/env python3
"""Scan official X posts for project progress → 「即将开盘」 signals.

Reads x_posts_cache.json + x_listing_posts_cache.json.
Classifies each project's recent official posts as:
  - already_live  → leave for prune/mark_launched (do NOT invent listing_at)
  - near_launch   → status 「即将启动」, listing_signal, x_progress facets
  - building      → optional softer readiness note (does not force 即将启动)

Merges into watchlist.json + push-radar/data/candidates.json (+ mirrors).
Never invents listing_at. Skips launched blocklist / 已开盘 cards.
Does not relax ca_gate — optional CA harvest from the same texts is written to
x_progress_ca_candidates.json for scan_listing_ca / build_ca_finds to verify.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
WATCHLIST = BASE / "watchlist.json"
X_CACHE = BASE / "x_posts_cache.json"
X_LISTING = BASE / "x_listing_posts_cache.json"
REMOVED = BASE / "removed_launched.json"
LAUNCHED = Path("/workspace/push-radar/data/launched.json")
CANDIDATES = Path("/workspace/push-radar/data/candidates.json")
OUT = BASE / "x_progress_latest.json"
CA_CANDS = BASE / "x_progress_ca_candidates.json"
MIRRORS = [
    Path("/workspace/publish-pages-data/candidates.json"),
    Path("/cursor/stores/store-b953e26e-8884-4159-b9a8-d2e6295761c8/publish-pages-data/candidates.json"),
]
SH = ZoneInfo("Asia/Shanghai")

EVM_RE = re.compile(r"(?<![a-fA-F0-9])(0x[a-fA-F0-9]{40})(?![a-fA-F0-9])")
SOL_RE = re.compile(r"\b([1-9A-HJ-NP-Za-km-z]{32,44})\b")
CA_CONTEXT = re.compile(
    r"(?:\bca\b|contract|合约|mint\s*address|token\s*address|合约地址|ca:|contract address)",
    re.I,
)

# Already live / trading — do not push into 即将开盘
ALREADY_LIVE = re.compile(
    r"(已开盘|开始交易|trading\s+now|trading\s+live|now\s+trading|"
    r"token\s+(is\s+)?live|\$\w+\s+is\s+(officially\s+)?live|"
    r"\$\w+\s+goes?\s+live|contract\s+address\s*[:=]|ca\s*[:=]\s*0x|"
    r"live\s+on\s+(uniswap|pancakeswap|raydium|pump\.fun)|"
    r"mint(?:ing)?\s+(?:is\s+)?(?:sold\s+out|complete|finished|ended)|"
    r"3333/\s*3333|minted\s+out|"
    r"launching\s+on\s+\w+\s+right\s+now|is\s+launching.{0,60}right\s+now|launches\s+today)",
    re.I,
)

# Near-launch / progress toward launch
NEAR_LAUNCH = re.compile(
    r"(即将开盘|马上开盘|即将发射|即将上线|即将开铸|开铸在即|今晚开盘|明天开盘|本周发射|"
    r"今晚发射|今日开盘|倒计时|即将揭晓|打新|流片窗口|创世打新|"
    r"whitelist\s+(?:is\s+)?clos(?:e|ing)|wl\s+clos|"
    r"mint\s+(?:is\s+)?(?:soon|imminent|this\s+week|tonight|tomorrow)|"
    r"public\s+(?:mint|launch)\s+(?:soon|this\s+week|tonight)|"
    r"almost\s+live|launch(?:ing)?\s+soon|opens?\s+at\s+launch|gates?\s+open\s+soon|"
    r"fully\s+live\s+soon|presale\s+whitelist|"
    r"tge\s+(?:soon|this\s+week|tonight|tomorrow|on\s+\w+)|"
    r"(?:token\s+)?(?:launch|launching|launches)\s+(?:soon|this\s+week|tonight|tomorrow|in\s+\d)|"
    r"goes?\s+live\s+(?:soon|tonight|tomorrow|this\s+week|in\s+\d)|"
    r"coming\s+soon|stand\s+by|ca\s+will\s+be\s+posted|"
    r"only\s+ca\s+will\s+be\s+posted|countdown|"
    r"finalising\s+(?:all\s+)?whitelist|finalizing\s+(?:all\s+)?whitelist|"
    r"mint\s+date|launch\s+date|开盘时间|发射倒计时|"
    r"mainnet\s+(?:soon|this\s+week)|"
    r"snapshot\s+(?:soon|this\s+week)|"
    r"tge\b|token\s+generation)",
    re.I,
)

BUILDING = re.compile(
    r"(audit\s+(?:complete|passed|done)|合约审计完成|代码冻结|code\s+freeze|"
    r"testnet\s+(?:live|launched)|主网准备|mainnet\s+ready|"
    r"contracts?\s+(?:deployed|are\s+live)|游戏完成|beta\s+(?:live|open)|"
    r"closed\s+beta|open\s+beta|playtest|"
    r"whitelist\s+(?:open|opens|is\s+open)|登记开启|"
    r"smart\s+contract(?:s)?\s+(?:ready|done)|"
    r"tokenomics\s+(?:final|ready)|经济模型确定)",
    re.I,
)

# AMA / Space — never treat as launch progress for 即将开盘 upgrade
NON_LAUNCH = re.compile(
    r"(?:\bAMA\b|Twitter\s+Space|X\s+Space|\bSpaces?\b|spaces\.x\.com|直播|播客)",
    re.I,
)


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def hkey(h: str | None) -> str:
    return (h or "").lower().lstrip("@").strip()


def load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def launched_handles() -> set[str]:
    out: set[str] = set()
    rem = load(REMOVED, {})
    entries = rem if isinstance(rem, list) else rem.get("removed") or rem.get("entries") or []
    if isinstance(rem, dict) and not entries:
        # sometimes {handle: {...}}
        for k, v in rem.items():
            if isinstance(v, dict) and (v.get("handle") or k):
                if v.get("restored"):
                    continue
                out.add(hkey(v.get("handle") or k))
    for e in entries if isinstance(entries, list) else []:
        if isinstance(e, dict) and not e.get("restored"):
            out.add(hkey(e.get("handle")))
    la = load(LAUNCHED, {})
    items = la if isinstance(la, list) else la.get("projects") or la.get("items") or la.get("launched") or []
    for i in items if isinstance(items, list) else []:
        if isinstance(i, dict):
            out.add(hkey(i.get("handle")))
    return {x for x in out if x}


def collect_posts(handle: str, x_users: dict, x_listing: dict) -> list[dict]:
    posts: list[dict] = []
    xu = None
    for k, v in x_users.items():
        if k.lower() == handle.lower():
            xu = v
            break
    if xu:
        for p in xu.get("posts") or []:
            if p.get("text"):
                posts.append(p)
    for p in x_listing.get(handle.lower()) or []:
        if isinstance(p, dict) and p.get("text"):
            posts.append(p)
    # newest first-ish
    def key(p):
        return p.get("created_at") or ""
    posts.sort(key=key, reverse=True)
    # dedupe by id or text
    seen = set()
    uniq = []
    for p in posts:
        k = p.get("id") or (p.get("text") or "")[:80]
        if k in seen:
            continue
        seen.add(k)
        uniq.append(p)
    return uniq[:40]


def classify_text(text: str) -> tuple[str, list[str]]:
    """Return (bucket, matched_keywords). bucket: already_live|near_launch|building|none"""
    if not text or not text.strip():
        return "none", []
    if NON_LAUNCH.search(text) and not NEAR_LAUNCH.search(text) and not ALREADY_LIVE.search(text):
        return "none", ["ama_space_skip"]
    hits: list[str] = []
    if ALREADY_LIVE.search(text):
        for m in ALREADY_LIVE.finditer(text):
            hits.append(m.group(0)[:40])
            if len(hits) >= 3:
                break
        return "already_live", hits
    if NEAR_LAUNCH.search(text):
        for m in NEAR_LAUNCH.finditer(text):
            hits.append(m.group(0)[:40])
            if len(hits) >= 3:
                break
        return "near_launch", hits
    if BUILDING.search(text):
        for m in BUILDING.finditer(text):
            hits.append(m.group(0)[:40])
            if len(hits) >= 3:
                break
        return "building", hits
    return "none", []


def extract_ca_candidates(text: str, url: str, handle: str) -> list[dict]:
    out = []
    if not text:
        return out
    for m in EVM_RE.finditer(text):
        addr = m.group(1)
        if addr.lower() == "0x" + "0" * 40:
            continue
        ctx = text[max(0, m.start() - 50) : m.end() + 50]
        # prefer near CA context; still keep if $TICKER nearby or explicit hex dump in announce
        strong = bool(CA_CONTEXT.search(ctx) or re.search(r"\$[A-Za-z]{2,12}", ctx))
        out.append({
            "type": "evm",
            "address": addr,
            "handle": handle,
            "snippet": ctx.replace("\n", " ")[:180],
            "evidence_url": url,
            "strong_context": strong,
            "source": "x_post",
        })
    for m in SOL_RE.finditer(text):
        addr = m.group(1)
        if addr.isalpha() and addr.lower() == addr:
            continue
        if not CA_CONTEXT.search(text[max(0, m.start() - 80) : m.end() + 80]):
            continue
        out.append({
            "type": "solana",
            "address": addr,
            "handle": handle,
            "snippet": text[max(0, m.start() - 50) : m.end() + 50].replace("\n", " ")[:180],
            "evidence_url": url,
            "strong_context": True,
            "source": "x_post",
        })
    return out


def apply_progress(proj: dict, verdict: dict) -> bool:
    """Mutate project/candidate row. Returns True if changed."""
    changed = False
    bucket = verdict.get("bucket")
    if bucket == "already_live":
        # mark signal only; prune/mark_launched owns 已开盘 move
        sig = f"x进度=疑似已开盘: {(verdict.get('snippet') or '')[:80]}"
        if proj.get("x_progress_bucket") != "already_live":
            proj["x_progress_bucket"] = "already_live"
            changed = True
        if proj.get("x_progress_signal") != sig:
            proj["x_progress_signal"] = sig
            proj["x_progress_evidence_url"] = verdict.get("evidence_url") or ""
            proj["x_progress_at"] = now_iso()
            changed = True
        return changed

    if bucket == "near_launch":
        if proj.get("status") not in ("即将启动", "mint进行中") and proj.get("listing") not in ("已开盘", "已上线"):
            # mint进行中 stays; 开发中/不明 → 即将启动
            if proj.get("status") != "即将启动":
                proj["status"] = "即将启动"
                changed = True
        sig = f"官推进度·即将开盘: {', '.join(verdict.get('hits') or [])}"
        if len(sig) > 160:
            sig = sig[:157] + "…"
        if proj.get("listing_signal") != sig and not str(proj.get("listing_signal") or "").startswith("官推进度"):
            # Prefer X progress over generic status=… placeholders
            old = proj.get("listing_signal") or ""
            if old.startswith("status=") or not old or "官推进度" in old:
                proj["listing_signal"] = sig
                changed = True
        if proj.get("x_progress_bucket") != "near_launch":
            proj["x_progress_bucket"] = "near_launch"
            changed = True
        proj["x_progress_signal"] = sig
        proj["x_progress_evidence_url"] = verdict.get("evidence_url") or ""
        proj["x_progress_snippet"] = (verdict.get("snippet") or "")[:200]
        proj["x_progress_at"] = now_iso()
        proj["x_progress_source"] = "x"
        # readiness facet for frontend/completion-style inclusion
        proj["x_launch_readiness"] = "high"
        proj["x_launch_readiness_label"] = "官推显示即将开盘"
        changed = True
        return changed

    if bucket == "building":
        if proj.get("x_progress_bucket") not in ("near_launch", "already_live"):
            proj["x_progress_bucket"] = "building"
            proj["x_progress_signal"] = f"官推进度·建设中: {', '.join(verdict.get('hits') or [])}"[:160]
            proj["x_progress_evidence_url"] = verdict.get("evidence_url") or ""
            proj["x_progress_at"] = now_iso()
            proj["x_launch_readiness"] = "medium"
            proj["x_launch_readiness_label"] = "官推显示推进中"
            # Stacked building signals can promote 开发中 → 即将启动 when ≥2 distinct hits
            if (
                proj.get("status") == "开发中"
                and len(verdict.get("hits") or []) >= 2
                and proj.get("listing") not in ("已开盘", "已上线")
            ):
                proj["status"] = "即将启动"
                proj["listing_signal"] = proj["x_progress_signal"]
            changed = True
        return changed

    return changed


def best_verdict(posts: list[dict]) -> dict | None:
    """Pick strongest recent signal. Prefer already_live > near_launch > building."""
    best = None
    rank = {"already_live": 3, "near_launch": 2, "building": 1, "none": 0}
    # Only consider posts from last ~14 days when created_at known; else keep
    cutoff = datetime.now(SH) - timedelta(days=14)
    for p in posts:
        text = p.get("text") or ""
        created = p.get("created_at")
        ref = None
        if created:
            try:
                ref = datetime.fromisoformat(created.replace("Z", "+00:00")).astimezone(SH)
            except Exception:
                ref = None
        if ref and ref < cutoff:
            continue
        bucket, hits = classify_text(text)
        if bucket == "none":
            continue
        cand = {
            "bucket": bucket,
            "hits": hits,
            "snippet": text.replace("\n", " ")[:200],
            "evidence_url": p.get("url") or "",
            "created_at": created,
        }
        if not best or rank[bucket] > rank[best["bucket"]]:
            best = cand
        elif rank[bucket] == rank[best["bucket"]] and (created or "") > (best.get("created_at") or ""):
            best = cand
    return best


def main() -> int:
    wl = load(WATCHLIST, {})
    projects = wl.get("projects") or []
    x_users = (load(X_CACHE, {}) or {}).get("users") or {}
    x_listing = (load(X_LISTING, {}) or {}).get("users") or {}
    launched = launched_handles()

    results = []
    upgraded = []
    already = []
    building = []
    ca_cands: list[dict] = []
    changed_n = 0

    for proj in projects:
        handle = (proj.get("handle") or "").lstrip("@")
        if not handle:
            continue
        if hkey(handle) in launched or proj.get("listing") in ("已开盘", "已上线"):
            continue
        posts = collect_posts(handle, x_users, x_listing)
        # always harvest CA strings from posts for later verify
        for p in posts:
            for c in extract_ca_candidates(p.get("text") or "", p.get("url") or "", handle):
                ca_cands.append(c)
        verdict = best_verdict(posts)
        row = {
            "handle": handle,
            "name": proj.get("name"),
            "posts_scanned": len(posts),
            "bucket": (verdict or {}).get("bucket") or "none",
            "hits": (verdict or {}).get("hits") or [],
            "evidence_url": (verdict or {}).get("evidence_url") or "",
            "snippet": (verdict or {}).get("snippet") or "",
            "prev_status": proj.get("status"),
        }
        if verdict:
            before = proj.get("status")
            if apply_progress(proj, verdict):
                changed_n += 1
            row["new_status"] = proj.get("status")
            if verdict["bucket"] == "near_launch":
                upgraded.append(row)
            elif verdict["bucket"] == "already_live":
                already.append(row)
            elif verdict["bucket"] == "building":
                building.append(row)
            if before != proj.get("status"):
                row["status_changed"] = f"{before}→{proj.get('status')}"
        results.append(row)

    if projects:
        wl["last_x_progress_at"] = now_iso()
        WATCHLIST.write_text(json.dumps(wl, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # candidates merge
    cand = load(CANDIDATES, {})
    rows = cand.get("candidates") if isinstance(cand, dict) else None
    cand_n = 0
    by_h = {hkey(r["handle"]): r for r in results if r.get("handle")}
    # map full project fields after apply
    proj_by = {hkey(p.get("handle")): p for p in projects}
    if isinstance(rows, list):
        for c in rows:
            h = hkey(c.get("handle"))
            if h in launched:
                continue
            p = proj_by.get(h)
            if not p:
                continue
            # copy progress fields
            for k in (
                "status", "listing_signal", "x_progress_bucket", "x_progress_signal",
                "x_progress_evidence_url", "x_progress_snippet", "x_progress_at",
                "x_progress_source", "x_launch_readiness", "x_launch_readiness_label",
            ):
                if k in p and c.get(k) != p.get(k):
                    c[k] = p[k]
                    cand_n += 1
        cand["x_progress_merged_at"] = now_iso()
        text = json.dumps(cand, ensure_ascii=False, indent=2) + "\n"
        CANDIDATES.write_text(text, encoding="utf-8")
        for m in MIRRORS:
            try:
                m.parent.mkdir(parents=True, exist_ok=True)
                m.write_text(text, encoding="utf-8")
            except Exception as e:
                print(f"WARN mirror {m}: {e}")

    # dedupe CA cands
    seen_ca = set()
    uniq_ca = []
    for c in ca_cands:
        k = (c.get("type"), (c.get("address") or "").lower(), hkey(c.get("handle")))
        if k in seen_ca:
            continue
        seen_ca.add(k)
        uniq_ca.append(c)

    doc = {
        "generated_at": now_iso(),
        "timezone": "Asia/Shanghai",
        "scanned": len(results),
        "near_launch": len(upgraded),
        "already_live": len(already),
        "building": len(building),
        "watchlist_fields_changed": changed_n,
        "candidates_fields_touched": cand_n,
        "upgraded": upgraded,
        "already_live_hits": already,
        "building_hits": building,
        "ca_candidates_count": len(uniq_ca),
    }
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    CA_CANDS.write_text(
        json.dumps({"generated_at": now_iso(), "candidates": uniq_ca}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"[{now_iso()}] x_progress scanned={len(results)} near_launch={len(upgraded)} "
        f"already_live={len(already)} building={len(building)} "
        f"status/fields_changed={changed_n} ca_cands={len(uniq_ca)} -> {OUT}"
    )
    for u in upgraded[:12]:
        print(f"  NEAR @{u['handle']} {u.get('status_changed') or u.get('prev_status')} | {', '.join(u.get('hits') or [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
