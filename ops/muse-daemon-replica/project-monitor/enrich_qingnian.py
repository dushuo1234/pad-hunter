#!/usr/bin/env python3
"""Enrich 青年大学习 freeform cards (name+handle only) to match 项目推送 field shape.

Fills chain / category / status / listing / risk / summary_cn / urls(site) from:
  1) name+handle+raw_text heuristics (always, free)
  2) optional X profile cache JSON or jina scrape of x.com/{handle}
  3) optional DeepSeek CLI `ds` for a short CN summary when still thin

Does NOT invent listing_at. Safe to re-run: never overwrites a non-blank
field with 未知/其他/不明/未开盘/empty unless --force.

Used by:
  - CLI: enrich blank 青年 rows then patch candidates
  - fetch_and_classify: heuristic pass right after parse_qingnian_card
  - tg_push_fast: post-sync enrich --new-only before merge
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SH = ZoneInfo("Asia/Shanghai")
TG = Path("/home/box/.tg-monitor")
PM = Path("/workspace/project-monitor")
PROJECTS = TG / "projects.json"
JSONL = TG / "projects.jsonl"
SITE_PROJECTS = Path("/workspace/push-radar/data/projects.json")
CANDIDATES = Path("/workspace/push-radar/data/candidates.json")
CAND_MIRROR = Path("/workspace/publish-pages-data/candidates.json")
CACHE_DIR = PM / "qingnian_enrich_cache"

BLANK_CHAIN = {"", "未知", "unknown", "其他", "其他/未知", "other"}
BLANK_CAT = {"", "其他", "未知", "other", "unknown"}
BLANK_STATUS = {"", "不明", "unknown", "unconfirmed"}
BLANK_LISTING = {"", "未开盘", "unknown", "不明"}
PUSH_ONLY_SUM = re.compile(r"^推送等级")

# --- heuristics -----------------------------------------------------------

CHAIN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(bnb\s*chain|binance\s*smart\s*chain|\bbsc\b|\bbnb\b|bnbchain|binance\s*(agent|square|wallet|intelligence)|四\.?meme|four\.?meme|opene?four|osbook)", re.I), "bsc"),
    (re.compile(r"\b(solana|\bsol\b|pump\.fun|letsbonk)", re.I), "Solana"),
    (re.compile(r"\b(ethereum|\beth\b|mainnet)\b", re.I), "ETH"),
    (re.compile(r"\bbase\b(?!\s*asset)", re.I), "Base"),
    (re.compile(r"\b(arc)\b|on\s*arc", re.I), "Arc"),
    (re.compile(r"\bink(\.fun|_|\s)|inkonchain|on\s*ink\b", re.I), "Ink"),
    (re.compile(r"robinhood|rh\s*chain", re.I), "robinhood"),
    (re.compile(r"xlayer|x\s*layer", re.I), "XLayer"),
    (re.compile(r"\bsui\b", re.I), "Sui"),
    (re.compile(r"\bnear\b", re.I), "NEAR"),
    (re.compile(r"\btron\b|\btrc20\b", re.I), "TRON"),
    (re.compile(r"\bhedera\b", re.I), "Hedera"),
]

CAT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"launchpad|发射台|launch\s*pad|token\s*launch|发币平台|bonding\s*curve|meme[s]?\s*→|graduate|graduated|\.fun\b.*ink|ink\.fun", re.I), "发射台"),
    (re.compile(r"\bgamefi\b|游戏|play\s*to\s*earn", re.I), "GameFi"),
    (re.compile(r"\bnft\b|铸造|mint", re.I), "NFT铸造"),
    (re.compile(r"\bdefi\b|借贷|amm|dex\b|swap", re.I), "DeFi协议"),
    (re.compile(r"ai\s*agent|agentic|agent\s*id|\.ai\b|intelligence\s*agent", re.I), "AI代理"),
    (re.compile(r"\bmeme\b|memecoin", re.I), "Meme币"),
    (re.compile(r"infra|基础设施|protocol\b|l2\b|rollup", re.I), "基础设施"),
    (re.compile(r"social|square\s*for|社交", re.I), "socialfi"),
]

KOL_HINT = re.compile(
    r"(机会留给|opportunity comes|中厅悟道|dm✈️|grind|kol|喊单|看盘|韭菜)",
    re.I,
)
LIVE_HINT = re.compile(r"\bis\s*live\b|已上线|正式上线|now\s*live|goes\s*live", re.I)
SOON_HINT = re.compile(r"即将上线|coming\s*soon|即将启动|即将开放|tba\b", re.I)
PERSONAL_URL = re.compile(r"linktr\.ee|gmgn\.ai|t\.me/", re.I)


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def _blob(*parts: Any) -> str:
    return " ".join(str(p or "") for p in parts)


def guess_chain(text: str) -> str | None:
    for pat, chain in CHAIN_PATTERNS:
        if pat.search(text):
            return chain
    return None


def guess_category(text: str, *, looks_kol: bool) -> str | None:
    if looks_kol:
        return None  # leave 其他 for KOLs unless strong product signal
    for pat, cat in CAT_PATTERNS:
        if pat.search(text):
            return cat
    return None


def guess_status(text: str) -> str | None:
    if SOON_HINT.search(text):
        return "即将启动"
    if LIVE_HINT.search(text):
        return "开发中"
    return None


def extract_site(urls: list[str] | None, profile_url: str | None = None) -> str | None:
    cands: list[str] = []
    if profile_url:
        cands.append(profile_url)
    for u in urls or []:
        cands.append(u)
    for u in cands:
        if not u or not str(u).startswith("http"):
            continue
        low = str(u).lower()
        if any(x in low for x in ("x.com", "twitter.com", "t.co/", "jina.ai")):
            continue
        if PERSONAL_URL.search(low) and "osbook" not in low:
            # keep linktree only if nothing else; prefer real product sites
            continue
        return str(u).rstrip("/")
    # fallback: allow linktree for KOLs
    for u in cands:
        if u and str(u).startswith("http") and "linktr.ee" in str(u).lower():
            return str(u).rstrip("/")
    return None


def is_thin_summary(s: str | None) -> bool:
    s = (s or "").strip()
    return (not s) or bool(PUSH_ONLY_SUM.match(s)) or len(s) < 12


def looks_like_kol(name: str, handle: str, bio: str, posts: str) -> bool:
    blob = _blob(name, handle, bio, posts)
    if KOL_HINT.search(blob):
        return True
    # short personal bios without product nouns
    product = re.search(r"launchpad|发射|protocol|platform|dapp|ledger|\$[A-Z]{2,10}\b|agent\s*square|osbook|meme|\.fun\b", blob, re.I)
    # No bio = no profile evidence; never call it KOL just from a one-word name.
    if not (bio or "").strip():
        return False
    if not product and len((bio or "").strip()) < 80 and not re.search(r"https?://", bio or ""):
        # name is a person-ish single token
        if re.fullmatch(r"[A-Za-z]{2,20}", (name or "").strip()) or name.strip() in {"bb", "Ryan", "Eason"}:
            return True
    return False


def build_risk(*, verified: bool | None, fans: int | None, looks_kol: bool, notes: str = "") -> str:
    bits: list[str] = []
    if looks_kol:
        bits.append("个人号/KOL，非项目官推")
    if verified:
        bits.append("官推已认证")
    if fans is not None and fans < 500 and not looks_kol:
        bits.append(f"粉丝较少({fans})")
    if notes:
        bits.append(notes)
    return "；".join(bits) if bits else "信息来自官推简介/近期帖，未实测合约。"


def heuristic_enrich(card: dict, profile: dict | None = None) -> dict:
    """Return a shallow-copied card with blank fields filled. Never invents listing_at."""
    out = dict(card)
    profile = profile or {}
    name = out.get("name") or ""
    handle = (out.get("twitter_handle") or "").lstrip("@")
    bio = profile.get("description") or ""
    posts = " ".join(profile.get("posts") or [])
    raw = out.get("raw_text") or ""
    blob = _blob(name, handle, bio, posts, raw, " ".join(out.get("urls") or []))

    looks_kol = looks_like_kol(name, handle, bio, posts)
    # Strong product overrides KOL guess
    if guess_category(blob, looks_kol=False) in {"发射台", "AI代理", "GameFi", "DeFi协议", "NFT铸造"}:
        if re.search(r"launchpad|发射台|square for|on\s+(arc|ink|bnb)|full-stack", blob, re.I):
            looks_kol = False

    chain = guess_chain(blob)
    cat = guess_category(blob, looks_kol=looks_kol)
    status = guess_status(blob)
    if looks_kol and not status:
        status = "不明"
    if not status and not looks_kol:
        status = "开发中"

    site = extract_site(out.get("urls"), profile.get("url") or None)
    if site:
        urls = list(out.get("urls") or [])
        if site not in urls:
            urls.append(site)
        out["urls"] = urls

    fans_n = profile.get("followers")
    if fans_n is None:
        m = re.search(r"粉丝\s*(\d+)", str(out.get("fans") or ""))
        fans_n = int(m.group(1)) if m else None

    verified = profile.get("verified")
    risk_notes = ""
    if "suspend" in blob.lower() or "暂停" in blob:
        risk_notes = "平台升级/暂停发币期间需关注"
    if "unaudited" in blob.lower() or "未审计" in blob:
        risk_notes = (risk_notes + "；" if risk_notes else "") + "提及未审计"

    # summary: prefer existing non-thin; else from bio; else name+chain+cat
    summary = out.get("summary_cn") or ""
    if is_thin_summary(summary):
        prefix = summary.strip()
        core = ""
        # Prefer a product-y post over a generic personal bio
        post0 = (profile.get("posts") or [None])[0] or ""
        bio_s = bio.strip().replace("\n", " ")
        if post0 and (looks_kol is False) and (
            len(bio_s) < 40
            or re.search(r"gambling|grind|机会|quantify", bio_s, re.I)
            or re.search(r"即将上线|launchpad|发射|square|live on|onchain", post0, re.I)
        ):
            core = post0.strip().replace("\n", " ")
        elif bio_s:
            core = bio_s
        elif post0:
            core = post0.strip().replace("\n", " ")
        if core:
            if len(core) > 120:
                core = core[:117] + "…"
            summary = f"{prefix} · {core}" if prefix and PUSH_ONLY_SUM.match(prefix) else core
        else:
            bits = [name]
            if chain:
                bits.append(f"链:{chain}")
            if cat:
                bits.append(cat)
            if looks_kol:
                bits.append("个人/KOL账号")
            summary = " · ".join(bits)

    def fill(key: str, val: Any, blank: set[str]) -> None:
        if val is None or val == "":
            return
        cur = out.get(key)
        if cur is None or str(cur).strip() in blank:
            out[key] = val

    if looks_kol:
        chain = None  # avoid mis-tagging KOL from casual chain mentions
        cat = None
    fill("chain", chain if chain else ("未知" if looks_kol else None), BLANK_CHAIN)
    fill("category", cat if cat else ("其他" if looks_kol else None), BLANK_CAT)
    fill("status", status, BLANK_STATUS)
    # listing: platforms without a stated TGE → 未提及; KOLs → 未开盘; else keep 未开盘
    if str(out.get("listing") or "").strip() in BLANK_LISTING:
        if looks_kol:
            out["listing"] = "未开盘"
        elif cat == "发射台" or (site and not looks_kol):
            out["listing"] = "未提及"
        else:
            out["listing"] = "未开盘"

    if not str(out.get("risk") or "").strip():
        out["risk"] = build_risk(
            verified=bool(verified) if verified is not None else None,
            fans=fans_n,
            looks_kol=looks_kol,
            notes=risk_notes,
        )

    if is_thin_summary(out.get("summary_cn")) and summary:
        out["summary_cn"] = summary

    out["enriched_at"] = now_iso()
    out["enriched_via"] = "qingnian_heuristic" + ("+profile" if profile else "")
    return out


def fetch_profile_jina(handle: str, timeout: int = 20) -> dict | None:
    handle = handle.lstrip("@")
    url = f"https://r.jina.ai/https://x.com/{handle}"
    req = urllib.request.Request(url, headers={"User-Agent": "PadHunterEnrich/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"jina_fail @{handle}: {type(e).__name__}", flush=True)
        return None
    # Parse markdown-ish profile
    desc = ""
    site = ""
    followers = None
    # bio often after @handle line
    m = re.search(r"@" + re.escape(handle) + r"\s*\n+([^\n]+)", text, re.I)
    if m:
        desc = m.group(1).strip()
    # followers
    fm = re.search(r"([\d,.]+)\s*Followers", text, re.I)
    if fm:
        try:
            followers = int(fm.group(1).replace(",", "").replace(".", ""))
        except ValueError:
            followers = None
    # website link near Joined
    for um in re.finditer(r"\[([^\]]+)\]\((https?://[^)]+)\)", text):
        label, href = um.group(1), um.group(2)
        low = href.lower()
        if any(x in low for x in ("x.com", "twitter.com", "jina.ai", "t.co/", "twimg.com")):
            continue
        if "joined" in label.lower():
            continue
        site = href
        break
    # collect a few post snippets
    posts = []
    for pm in re.finditer(r"\[\d+[hm]\]|\[\w+ \d+\]", text):
        pass
    # simpler: lines that look like tweet body after handle mentions — take up to 3 long lines
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 40 or line.startswith("[") or line.startswith("#") or line.startswith("!"):
            continue
        if "Log in" in line or "Sign up" in line:
            continue
        if handle.lower() in line.lower() and len(line) < 60:
            continue
        posts.append(line[:240])
        if len(posts) >= 4:
            break
    return {
        "description": desc,
        "url": site,
        "followers": followers,
        "verified": None,
        "posts": posts,
        "source": "jina",
    }


def ds_summary(prompt_blob: str) -> str | None:
    ds = os.environ.get("DS_BIN") or "ds"
    prompt = (
        "用一句中文（≤40字）概括该加密项目/账号，不要编造开盘时间，不要英文："
        + prompt_blob[:600]
    )
    try:
        proc = subprocess.run(
            [ds, prompt],
            capture_output=True,
            text=True,
            timeout=45,
        )
    except Exception:
        return None
    out = (proc.stdout or "").strip()
    if not out or proc.returncode != 0:
        return None
    # first non-empty line
    for line in out.splitlines():
        line = line.strip()
        if line:
            return line[:80]
    return None


def load_profile_cache(handle: str, cache_files: list[Path]) -> dict | None:
    h = handle.lstrip("@").lower()
    for path in cache_files:
        if not path.exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(doc, dict):
            continue
        for k, v in doc.items():
            if k.lstrip("@").lower() == h and isinstance(v, dict):
                return v
    return None


def needs_enrich(card: dict) -> bool:
    if (card.get("source_channel") or "") != "青年大学习":
        return False
    if str(card.get("chain") or "") in BLANK_CHAIN:
        return True
    if str(card.get("category") or "") in BLANK_CAT:
        return True
    if is_thin_summary(card.get("summary_cn")):
        return True
    if not str(card.get("risk") or "").strip():
        return True
    return False


def enrich_card(
    card: dict,
    *,
    profile: dict | None = None,
    use_jina: bool = False,
    use_ds: bool = False,
) -> dict:
    handle = (card.get("twitter_handle") or "").lstrip("@")
    prof = profile
    if prof is None and use_jina and handle:
        prof = fetch_profile_jina(handle)
    out = heuristic_enrich(card, prof)
    if use_ds and is_thin_summary(out.get("summary_cn")):
        blob = _blob(out.get("name"), handle, (prof or {}).get("description"), out.get("summary_cn"))
        s = ds_summary(blob)
        if s:
            prefix = card.get("summary_cn") or ""
            if prefix and PUSH_ONLY_SUM.match(prefix.strip()):
                out["summary_cn"] = f"{prefix.strip()} · {s}"
            else:
                out["summary_cn"] = s
            out["enriched_via"] = (out.get("enriched_via") or "") + "+ds"
    return out


def write_projects_and_jsonl(by_key: dict[str, dict]) -> None:
    # Preserve insertion: rebuild list sorted by date desc like snapshot
    if not by_key:
        # Never clobber a non-empty snapshot with an empty map (load failure / filter bug).
        if PROJECTS.exists() and PROJECTS.stat().st_size > 10:
            print("write_skip: empty by_key, keeping existing projects", flush=True)
            return
    items = list(by_key.values())
    items.sort(key=lambda x: x.get("date_iso") or "", reverse=True)
    text = json.dumps(items, ensure_ascii=False, indent=2) + "\n"
    PROJECTS.write_text(text, encoding="utf-8")
    try:
        os.chmod(PROJECTS, 0o600)
    except OSError:
        pass
    lines = [json.dumps(by_key[k], ensure_ascii=False) for k in sorted(by_key.keys())]
    JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(JSONL, 0o600)
    except OSError:
        pass
    # site snapshot
    try:
        SITE_PROJECTS.parent.mkdir(parents=True, exist_ok=True)
        SITE_PROJECTS.write_text(json.dumps(items, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.chmod(SITE_PROJECTS, 0o644)
    except OSError as e:
        print(f"site_projects_warn: {e}", flush=True)


def storage_key(obj: dict) -> str:
    peer = obj.get("source_peer")
    mid = obj.get("message_id")
    if peer in (None, "", 0):
        return str(int(mid))
    return f"{int(peer)}:{int(mid)}"


def load_jsonl_map() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not JSONL.exists():
        return out
    for ln in JSONL.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            o = json.loads(ln)
        except Exception:
            continue
        out[storage_key(o)] = o
    return out


BLANK_CAND_FIELDS = {
    "chain": BLANK_CHAIN,
    "category": BLANK_CAT,
    "status": BLANK_STATUS,
    "listing": BLANK_LISTING,
}


def patch_candidates_from_projects(projects: list[dict]) -> dict:
    """Update existing candidate rows when project fields are richer."""
    if not CANDIDATES.exists():
        return {"updated": 0}
    cand = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    rows = cand.get("candidates") or []
    by_h = {}
    for p in projects:
        h = (p.get("twitter_handle") or "").lstrip("@").lower()
        if h:
            by_h[h] = p
    updated = 0
    for c in rows:
        h = (c.get("handle") or "").lstrip("@").lower()
        p = by_h.get(h)
        if not p:
            continue
        changed = False
        for field, blank in BLANK_CAND_FIELDS.items():
            pv = p.get(field)
            if pv is None or str(pv).strip() in blank:
                continue
            if str(c.get(field) or "").strip() in blank:
                c[field] = pv
                changed = True
        if p.get("risk") and not str(c.get("risk") or "").strip():
            c["risk"] = p["risk"]
            changed = True
        sum_ = p.get("summary_cn") or p.get("summary_en") or ""
        if sum_ and (is_thin_summary(c.get("bio")) or is_thin_summary(c.get("why"))):
            if is_thin_summary(c.get("bio")):
                c["bio"] = sum_
            if is_thin_summary(c.get("why")):
                c["why"] = sum_
            changed = True
        site = None
        for u in p.get("urls") or []:
            if u and "x.com" not in u and "twitter.com" not in u and str(u).startswith("http"):
                site = u
                break
        if site and not c.get("site"):
            c["site"] = site
            changed = True
        if not c.get("tweet_url") and (p.get("x_url") or h):
            c["tweet_url"] = p.get("x_url") or f"https://x.com/{p.get('twitter_handle') or h}"
            changed = True
        if changed:
            updated += 1
    if updated:
        cand["updated_at"] = now_iso()
        cand["qingnian_enriched_at"] = now_iso()
        text = json.dumps(cand, ensure_ascii=False, indent=2) + "\n"
        CANDIDATES.write_text(text, encoding="utf-8")
        try:
            CAND_MIRROR.parent.mkdir(parents=True, exist_ok=True)
            CAND_MIRROR.write_text(text, encoding="utf-8")
        except OSError:
            pass
    return {"updated": updated, "candidates": len(rows)}


def run_batch(
    *,
    handles: set[str] | None,
    limit: int,
    use_jina: bool,
    use_ds: bool,
    cache_files: list[Path],
    new_only: bool,
) -> dict:
    by_key = load_jsonl_map()
    # Prefer latest card per handle among 青年
    latest: dict[str, tuple[str, dict]] = {}
    for k, o in by_key.items():
        if (o.get("source_channel") or "") != "青年大学习":
            continue
        h = (o.get("twitter_handle") or "").lstrip("@").lower()
        if not h:
            continue
        if handles and h not in handles:
            continue
        if not needs_enrich(o) and not (handles and h in handles):
            continue
        prev = latest.get(h)
        if not prev or (o.get("date_iso") or "") > (prev[1].get("date_iso") or ""):
            latest[h] = (k, o)

    items = sorted(latest.items(), key=lambda kv: kv[1][1].get("date_iso") or "", reverse=True)
    if limit and not handles:
        items = items[:limit]

    enriched_handles: list[str] = []
    samples: list[dict] = []
    for h, (key, card) in items:
        prof = load_profile_cache(h, cache_files)
        # when handles explicitly given, allow enrich even if already filled
        out = enrich_card(card, profile=prof, use_jina=use_jina and prof is None, use_ds=use_ds)
        # also update ALL jsonl rows for same handle that are still blank
        for k2, o2 in list(by_key.items()):
            if (o2.get("twitter_handle") or "").lstrip("@").lower() != h:
                continue
            if (o2.get("source_channel") or "") != "青年大学习":
                continue
            merged = enrich_card(o2, profile=prof, use_jina=False, use_ds=False)
            # copy filled fields from `out` (best)
            for fld in ("chain", "category", "status", "listing", "risk", "summary_cn", "urls", "enriched_at", "enriched_via"):
                if out.get(fld):
                    cur = merged.get(fld)
                    blank = {
                        "chain": BLANK_CHAIN,
                        "category": BLANK_CAT,
                        "status": BLANK_STATUS,
                        "listing": BLANK_LISTING,
                    }.get(fld)
                    if blank is not None and (cur is None or str(cur).strip() in blank):
                        merged[fld] = out[fld]
                    elif fld in ("risk", "summary_cn", "urls", "enriched_at", "enriched_via"):
                        if fld == "summary_cn" and is_thin_summary(cur):
                            merged[fld] = out[fld]
                        elif fld == "risk" and not str(cur or "").strip():
                            merged[fld] = out[fld]
                        elif fld == "urls":
                            merged[fld] = out[fld]
                        elif fld.startswith("enriched"):
                            merged[fld] = out[fld]
            by_key[k2] = merged
        enriched_handles.append(h)
        samples.append({
            "name": out.get("name"),
            "handle": h,
            "chain": out.get("chain"),
            "category": out.get("category"),
            "status": out.get("status"),
            "listing": out.get("listing"),
            "risk": (out.get("risk") or "")[:60],
            "summary_cn": (out.get("summary_cn") or "")[:80],
            "site": extract_site(out.get("urls")),
        })

    write_projects_and_jsonl(by_key)
    patch = patch_candidates_from_projects(list(by_key.values()))
    return {
        "enriched": len(enriched_handles),
        "handles": enriched_handles,
        "samples": samples,
        "candidates_patched": patch.get("updated", 0),
        "at": now_iso(),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich 青年大学习 project cards")
    ap.add_argument("--handles", default="", help="comma-separated handles (default: blank 青年)")
    ap.add_argument("--limit", type=int, default=15, help="max blank handles when --handles empty")
    ap.add_argument("--jina", action="store_true", help="fetch X profile via jina when no cache")
    ap.add_argument("--ds", action="store_true", help="use DeepSeek CLI for thin summaries")
    ap.add_argument("--cache", action="append", default=[], help="profile cache JSON path")
    ap.add_argument("--new-only", action="store_true", help="alias: only needs_enrich (default behavior)")
    args = ap.parse_args()

    handles = {h.strip().lstrip("@").lower() for h in args.handles.split(",") if h.strip()} or None
    cache_files = [Path(p) for p in args.cache]
    default_cache = CACHE_DIR / "profiles_7.json"
    if default_cache.exists() and default_cache not in cache_files:
        cache_files.append(default_cache)
    # also any *.json in cache dir
    if CACHE_DIR.exists():
        for p in CACHE_DIR.glob("*.json"):
            if p not in cache_files:
                cache_files.append(p)

    result = run_batch(
        handles=handles,
        limit=args.limit,
        use_jina=args.jina,
        use_ds=args.ds,
        cache_files=cache_files,
        new_only=True,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
