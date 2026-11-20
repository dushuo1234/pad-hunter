#!/usr/bin/env python3
"""When ca_finds has a medium+/high CA for a still-active radar handle, soft-move it to 已开盘.

Unlike prune_launched (which requires trading wording), a locked CA for a watched
handle is enough: user expects Hookereum-style locks to leave 即将开盘 immediately.

Updates local:
  - removed_launched.json (blocklist + launched feed source)
  - watchlist.json
  - push-radar/data/{candidates,projects,launched}.json
  - publish-pages-data mirrors of those three

Does not call GitHub; caller should publish via publish_pages_file / publish_ca_finds.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
CA_FINDS = BASE / "ca_finds.json"
WATCHLIST = BASE / "watchlist.json"
REMOVED = BASE / "removed_launched.json"
DATA = Path("/workspace/push-radar/data")
PUBLISH = Path("/workspace/publish-pages-data")
STORE = None  # bot store publish-pages-data is not writable from this agent
CANDIDATES = DATA / "candidates.json"
PROJECTS = DATA / "projects.json"
LAUNCHED = DATA / "launched.json"
TZ = ZoneInfo("Asia/Shanghai")

CONF_OK = {"medium", "high", "confirmed"}


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def dump(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def hkey(h: str | None) -> str:
    return (h or "").lstrip("@").strip().lower()


def _is_wallet_find(f: dict) -> bool:
    kind = (f.get("kind") or "").lower()
    note = (f.get("note") or "").lower()
    if kind == "wallet":
        return True
    if "eoa/wallet" in note or "likely a wallet" in note:
        return True
    return False


def _qualifies(f: dict, conf: str) -> bool:
    """Token/contract CA locks only — not wallets, not unprobed infra JS addrs."""
    if _is_wallet_find(f):
        return False
    # HARD CA GATE: must be a verified ERC20 / SPL mint
    try:
        from ca_gate import verify_address
        if not verify_address(f.get("address") or "", f.get("chain")).get("is_token"):
            return False
    except Exception:
        return False
    kind = (f.get("kind") or "").lower()
    label = (f.get("label_zh") or "")
    if kind in ("wallet", "unknown") or label == "扫出钱包":
        return False
    note = (f.get("note") or "").lower()
    if "no bytecode on probed" in note or "placeholder" in note or "infra" in note:
        # site JS config addresses with empty code ≠ token launch
        return False
    src = (f.get("source") or "").lower()
    origins = " ".join(
        str((s or {}).get("origin") or "") for s in (f.get("sources") or []) if isinstance(s, dict)
    ).lower()
    if "onchain_lock" in src or "onchain_lock" in origins or "solana_lock" in origins:
        return True
    if kind == "contract" and conf in CONF_OK:
        # Static bio/site/JS contract: only 已开盘 if it actually trades (DexScreener).
        # Deployed-but-not-trading = pre-launch CA (keep in 即将开盘); NFT contracts never trade.
        try:
            from trading_check import check_trading
            return bool(check_trading(f.get("address") or "", f.get("chain")).get("trading"))
        except Exception:
            return False
    # High-confidence Solana mint / pump (non-EVM) — no eth_getCode kind
    addr = (f.get("address") or "")
    if conf in {"high", "confirmed"} and not (addr.lower().startswith("0x") and len(addr) == 42):
        return True
    # High EVM without kind: do NOT auto-launch (must be classified contract first)
    return False


def active_ca_by_handle() -> dict[str, dict]:
    doc = load(CA_FINDS, {})
    out: dict[str, dict] = {}
    for f in doc.get("finds") or []:
        if not isinstance(f, dict):
            continue
        conf = (f.get("confidence") or "").lower() or "medium"
        if conf not in CONF_OK:
            continue
        if not _qualifies(f, conf):
            continue
        h = hkey(f.get("handle"))
        addr = (f.get("address") or f.get("ca") or "").strip()
        if not h or not addr:
            continue
        prev = out.get(h)
        rank = {"confirmed": 3, "high": 2, "medium": 1}.get(conf, 0)
        prev_rank = {"confirmed": 3, "high": 2, "medium": 1}.get((prev or {}).get("confidence") or "", 0)
        if prev is None or rank >= prev_rank:
            out[h] = {
                "handle": h,
                "project": f.get("project") or h,
                "ca": addr,
                "ca_chain": f.get("chain"),
                "confidence": conf,
                "detected_at": f.get("detected_at"),
                "note": f.get("note"),
                "source": f.get("source") or "ca_finds",
            }
    return out


def mirror_data_files() -> None:
    for name in ("candidates.json", "projects.json", "launched.json"):
        src = DATA / name
        if not src.is_file():
            continue
        for root in (PUBLISH,):
            try:
                root.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, root / name)
            except OSError as e:
                print(f"[mark_launched_from_ca] mirror warn {root/name}: {e}", flush=True)


def mark() -> dict:
    ts = now_iso()
    ca_map = active_ca_by_handle()
    wl = load(WATCHLIST, {})
    projects = list(wl.get("projects") or [])
    removed_doc = load(REMOVED, {"items": []})
    if isinstance(removed_doc, list):
        removed_doc = {"items": removed_doc}
    removed_items = removed_doc.setdefault("items", [])
    already_blocked = {hkey(e.get("handle")) for e in removed_items if not e.get("restored")}
    restored = {hkey(e.get("handle")) for e in removed_items if e.get("restored")}
    by_h = {hkey(p.get("handle")): p for p in projects}

    newly = []
    for h, info in ca_map.items():
        if h in already_blocked or h in restored:
            continue
        # Only mark if still on radar (watchlist) OR still in candidates
        p = by_h.get(h)
        cand = load(CANDIDATES, {})
        in_cand = False
        if isinstance(cand, dict):
            in_cand = any(hkey(c.get("handle")) == h for c in (cand.get("candidates") or []) if isinstance(c, dict))
        if not p and not in_cand:
            continue
        p = p or {"handle": info["handle"], "name": info["project"]}
        entry = {
            "project": p.get("name") or info["project"],
            "handle": p.get("handle") or info["handle"],
            "chain": p.get("chain") or info.get("ca_chain"),
            "category": p.get("category"),
            "x_url": p.get("x_url") or f"https://x.com/{info['handle']}",
            "sites": p.get("sites") or [],
            "listing_at": info.get("detected_at") or ts,
            "ca": info["ca"],
            "ca_chain": info.get("ca_chain") or p.get("ca_chain"),
            "reason": "onchain_ca_lock",
            "evidence": (
                f"CA locked ({info.get('confidence')}): {info['ca']} "
                f"via {info.get('source')}; auto-moved out of 即将开盘"
            ),
            "evidence_url": p.get("x_url") or f"https://x.com/{info['handle']}",
            "removed_at": ts,
            "restored": False,
            "snapshot": p,
        }
        removed_items.append(entry)
        newly.append(entry)

    block = {hkey(e.get("handle")) for e in removed_items if not e.get("restored")}
    removed_doc["updated_at"] = ts
    removed_doc["note"] = (
        "Soft-deleted launched projects. Handles here are a blocklist for "
        "watchlist/candidates/projects. Set restored=true to bring one back. "
        "onchain_ca_lock = medium+/high CA find for a radar handle."
    )
    dump(REMOVED, removed_doc)

    before_w = len(projects)
    wl["projects"] = [p for p in projects if hkey(p.get("handle")) not in block]
    wl["count"] = len(wl["projects"])
    wl["last_prune_at"] = ts
    dump(WATCHLIST, wl)

    cand = load(CANDIDATES, None)
    before_c = after_c = None
    if isinstance(cand, dict) and isinstance(cand.get("candidates"), list):
        before_c = len(cand["candidates"])
        cand["candidates"] = [c for c in cand["candidates"] if hkey(c.get("handle")) not in block]
        for i, c in enumerate(cand["candidates"], 1):
            c["rank"] = i
        after_c = len(cand["candidates"])
        cand["pruned_launched_at"] = ts
        dump(CANDIDATES, cand)

    pj = load(PROJECTS, None)
    before_p = after_p = None
    if isinstance(pj, list):
        before_p = len(pj)
        pj = [x for x in pj if hkey(x.get("twitter_handle") or x.get("handle")) not in block]
        after_p = len(pj)
        dump(PROJECTS, pj)

    latest: dict[str, dict] = {}
    for e in removed_items:
        if e.get("restored"):
            continue
        k = hkey(e.get("handle"))
        if k not in latest or (e.get("removed_at") or "") > (latest[k].get("removed_at") or ""):
            latest[k] = e
    items = sorted(latest.values(), key=lambda e: e.get("removed_at") or "", reverse=True)
    launched = {
        "generated_at": ts,
        "count": len(items),
        "items": [
            {
                k: e.get(k)
                for k in (
                    "project",
                    "handle",
                    "chain",
                    "category",
                    "x_url",
                    "sites",
                    "listing_at",
                    "ca",
                    "ca_chain",
                    "reason",
                    "launched_reason",
                    "evidence",
                    "evidence_url",
                    "removed_at",
                )
            }
            for e in items
        ],
    }
    dump(LAUNCHED, launched)
    mirror_data_files()

    wb_stats = {"before": None, "after": None, "dropped": []}
    try:
        from launched_blocklist import prune_workbench
        wb_stats = prune_workbench(block)
    except Exception as e:
        print(f"[mark_launched_from_ca] workbench prune warn: {e}", flush=True)
    try:  # cloud workbench (api.adualpha.win): push blocklist, drop launched pins, re-mirror
        from cf_workbench_prune import run as _cf_run
        _cf = _cf_run(mirror=True, push=True)
        print(f"[mark_launched_from_ca] cf_workbench ok={_cf.get('ok')} dropped={_cf.get('worker_dropped')} "
              f"tombstoned={_cf.get('tombstoned')} cloud_pins={_cf.get('cloud_pins')} err={_cf.get('error')}", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"[mark_launched_from_ca] cf_workbench warn (non-fatal): {e}", flush=True)

    summary = {
        "newly": len(newly),
        "handles": [e.get("handle") for e in newly],
        "watchlist": f"{before_w}->{len(wl['projects'])}",
        "candidates": f"{before_c}->{after_c}",
        "projects": f"{before_p}->{after_p}",
        "launched_count": launched["count"],
        "workbench": f"{wb_stats.get('before')}->{wb_stats.get('after')}",
        "workbench_dropped": [d.get("handle") for d in (wb_stats.get("dropped") or [])],
    }
    print(f"[mark_launched_from_ca] {ts} newly={summary['newly']} {summary['handles']}", flush=True)
    print(f"  workbench {summary.get('workbench')} dropped={summary.get('workbench_dropped')}", flush=True)
    print(
        f"  watchlist {summary['watchlist']} candidates {summary['candidates']} "
        f"projects {summary['projects']} launched={summary['launched_count']}",
        flush=True,
    )
    return summary


def publish_site_data() -> int:
    """Best-effort Contents API publish for launched/candidates/projects."""
    from publish_pages_file import put_file

    rc = 0
    mapping = [
        (LAUNCHED, "public/data/launched.json", "data: launched auto"),
        (CANDIDATES, "public/data/candidates.json", "data: candidates auto (ca-launched)"),
        (PROJECTS, "public/data/projects.json", "data: projects auto (ca-launched)"),
    ]
    for local, remote, msg in mapping:
        if not local.is_file():
            continue
        try:
            n = put_file(local, remote, message=msg)
            if n != 0:
                rc = n
        except Exception as e:
            print(f"[mark_launched_from_ca] publish {remote} failed: {e}", flush=True)
            rc = 2
    return rc



def force_launch(*, handle: str, project: str | None, ca: str | None, ca_chain: str | None,
                 reason: str, evidence: str, evidence_url: str | None = None) -> bool:
    """Put handle into removed_launched (restored=false). Overrides a prior restore.
    Returns True if state changed. Caller runs mark() to prune lists."""
    h = hkey(handle)
    if not h:
        return False
    ts = now_iso()
    doc = load(REMOVED, {"items": []})
    if isinstance(doc, list):
        doc = {"items": doc}
    items = doc.setdefault("items", [])
    for e in items:
        if hkey(e.get("handle")) == h:
            if not e.get("restored") and e.get("reason") == reason:
                return False
            e.update({"restored": False, "reason": reason, "launched_reason": reason, "evidence": evidence,
                      "ca": ca or e.get("ca"), "ca_chain": ca_chain or e.get("ca_chain"),
                      "relaunched_at": ts, "removed_at": ts})
            if evidence_url:
                e["evidence_url"] = evidence_url
            dump(REMOVED, doc)
            return True
    wl = load(WATCHLIST, {})
    snap = next((x for x in wl.get("projects") or [] if hkey(x.get("handle")) == h), None)
    if snap is None:
        cand = load(CANDIDATES, {})
        snap = next((x for x in (cand.get("candidates") or []) if hkey(x.get("handle")) == h), None) or {}
    items.append({
        "project": project or snap.get("name") or handle,
        "handle": snap.get("handle") or handle,
        "chain": snap.get("chain") or ca_chain,
        "category": snap.get("category"),
        "x_url": snap.get("x_url") or f"https://x.com/{handle}",
        "sites": snap.get("sites") or [],
        "listing_at": ts,
        "ca": ca, "ca_chain": ca_chain,
        "reason": reason, "launched_reason": reason, "evidence": evidence,
        "evidence_url": evidence_url or snap.get("x_url") or f"https://x.com/{handle}",
        "removed_at": ts, "restored": False, "snapshot": snap,
    })
    dump(REMOVED, doc)
    return True


def sweep_trading(dry: bool = False) -> list[dict]:
    """Every active contract CA (ca_finds + watchlist.ca) that is already trading
    on DexScreener for >= MIN_AGE_HOURS -> 已开盘 (reason=already_trading)."""
    from trading_check import check_trading
    seen: set[tuple[str, str]] = set()
    todo: list[dict] = []
    doc = load(CA_FINDS, {})
    for f in doc.get("finds") or []:
        if _is_wallet_find(f) or (f.get("kind") or "").lower() in ("wallet",):
            continue
        if (f.get("confidence") or "") == "low":
            continue
        todo.append({"handle": f.get("handle"), "project": f.get("project"),
                     "ca": f.get("address"), "chain": f.get("chain")})
    for x in load(WATCHLIST, {}).get("projects") or []:
        if x.get("ca"):
            todo.append({"handle": x.get("handle"), "project": x.get("name"),
                         "ca": x.get("ca"), "chain": x.get("ca_chain")})
    moved = []
    for it in todo:
        key = (hkey(it["handle"]), (it["ca"] or "").lower())
        if not it["ca"] or key in seen:
            continue
        seen.add(key)
        r = check_trading(it["ca"], it.get("chain"))
        if not r.get("launched_old"):
            continue
        ev = (f"CA {it['ca']} already trading on {r.get('chain')} since {r.get('first_pair_at')} "
              f"(age {r.get('age_hours')}h, liq ${r.get('liquidity_usd')}, vol24 ${r.get('volume_h24')}) "
              f"via DexScreener; auto-moved to 已开盘")
        row = {**it, "trading": r, "evidence": ev}
        if not dry and force_launch(handle=it["handle"], project=it["project"], ca=it["ca"],
                                    ca_chain=r.get("chain") or it.get("chain"),
                                    reason="already_trading", evidence=ev,
                                    evidence_url=r.get("dex_url")):
            row["changed"] = True
        moved.append(row)
    return moved

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--publish", action="store_true", help="Also push launched/candidates/projects to GitHub")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--sweep-trading", action="store_true",
                    help="Move any project whose CA already trades (DexScreener) to 已开盘")
    args = ap.parse_args()
    if args.sweep_trading:
        moved = sweep_trading(dry=args.dry_run)
        for m in moved:
            print(f"[sweep_trading] {'DRY ' if args.dry_run else ''}{m['handle']} {m['ca']} "
                  f"{m['trading'].get('chain')} age={m['trading'].get('age_hours')}h "
                  f"vol24={m['trading'].get('volume_h24')} changed={m.get('changed', False)}", flush=True)
        if args.dry_run:
            return 0
    if args.dry_run:
        ca_map = active_ca_by_handle()
        wl = load(WATCHLIST, {})
        blocked = {hkey(e.get("handle")) for e in load(REMOVED, {"items": []}).get("items", []) if not e.get("restored")}
        todo = []
        for h, info in ca_map.items():
            if h in blocked:
                continue
            if any(hkey(p.get("handle")) == h for p in (wl.get("projects") or [])):
                todo.append(info)
        print(json.dumps({"would_mark": todo}, ensure_ascii=False, indent=2))
        return 0
    try:
        summary = mark()
    except Exception as e:
        print(f"[mark_launched_from_ca] error: {e}", flush=True)
        return 2
    if args.publish and summary.get("newly", 0) >= 0:
        # Always try publish after mark so Pages catches up even if newly=0 but files drifted
        return publish_site_data()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
