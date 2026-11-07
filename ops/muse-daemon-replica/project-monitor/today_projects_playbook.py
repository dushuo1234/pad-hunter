#!/usr/bin/env python3
"""为今日项目清单生成/刷新 playbook（玩法、参与需求、步骤、风险、来源）。

规则：
  - 缺 playbook 或 playbook.updated_at 超过 6h 才刷新
  - 抓官网 + 聚合 X 缓存/官推原文；可用 ds(DeepSeek) 结构化中文，否则启发式
  - 绝不编造合约地址或未证实费用
  - 写回 today_projects.json 并镜像；可选 --publish
"""
from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
OUT = BASE / "today_projects.json"
X_CACHE = BASE / "x_posts_cache.json"
X_LISTING = BASE / "x_listing_posts_cache.json"
X_INBOX = BASE / "alerts" / "x_inbox"
MIRRORS = [
    Path("/workspace/push-radar/data/today_projects.json"),
    Path("/workspace/publish-pages-data/today_projects.json"),
]
TZ = ZoneInfo("Asia/Shanghai")
STALE_H = 6
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36 PadHunterToday/1.0"


def now() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone(TZ).isoformat(timespec="seconds")


def norm(h: str | None) -> str:
    return (h or "").strip().lstrip("@").lower()


def load(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default if default is not None else {}


def save_doc(doc: dict) -> None:
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for dest in MIRRORS:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT, dest)
        except OSError as e:
            print(f"[playbook] mirror warn {dest}: {e}", flush=True)


def parse_updated(pb: dict | None) -> datetime | None:
    if not isinstance(pb, dict):
        return None
    s = pb.get("updated_at")
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except Exception:
        return None


def needs_refresh(pb: dict | None, *, force: bool) -> bool:
    if force or not pb:
        return True
    u = parse_updated(pb)
    if not u:
        return True
    return now() - u > timedelta(hours=STALE_H)


def fetch_site(url: str | None) -> str:
    if not url or not str(url).startswith("http"):
        return ""
    try:
        import urllib.request

        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=18) as resp:
            raw = resp.read(200_000).decode("utf-8", "ignore")
    except Exception as e:
        return f"[fetch_error] {e}"
    raw = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", raw)
    raw = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html_lib.unescape(raw)
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:4000]


def x_posts_for(handle: str) -> list[str]:
    key = norm(handle)
    texts: list[str] = []
    xu = (load(X_CACHE, {}) or {}).get("users") or {}
    for k, v in xu.items():
        if norm(k) != key or not isinstance(v, dict):
            continue
        for p in v.get("posts") or []:
            if isinstance(p, dict):
                t = (p.get("text") or p.get("full_text") or "").strip()
                if t:
                    texts.append(t)
    xl = (load(X_LISTING, {}) or {}).get("users") or {}
    for k, v in xl.items():
        if norm(k) != key:
            continue
        posts = v if isinstance(v, list) else (v or {}).get("posts") or []
        for p in posts:
            if isinstance(p, dict):
                t = (p.get("text") or p.get("full_text") or "").strip()
                if t:
                    texts.append(t)
    if X_INBOX.is_dir():
        for f in list(X_INBOX.glob("*.json"))[:30] + list((X_INBOX / "done").glob("*.json"))[:30]:
            try:
                blob = f.read_text(encoding="utf-8", errors="ignore")
                if key not in blob.lower() and handle.lstrip("@").lower() not in blob.lower():
                    continue
                data = json.loads(blob)
            except Exception:
                continue
            # best-effort extract texts
            stack = [data]
            while stack:
                cur = stack.pop()
                if isinstance(cur, dict):
                    t = cur.get("text") or cur.get("full_text")
                    if isinstance(t, str) and t.strip():
                        texts.append(t.strip())
                    stack.extend(cur.values())
                elif isinstance(cur, list):
                    stack.extend(cur)
    # dedupe keep order
    seen, out = set(), []
    for t in texts:
        k = t[:120]
        if k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out[:40]


def ds_available() -> bool:
    from shutil import which

    return which("ds") is not None


def call_ds(prompt: str) -> str | None:
    try:
        proc = subprocess.run(
            ["ds", "-m", "deepseek-flash", prompt],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except Exception:
        return None


def heuristic_playbook(item: dict, site_text: str, posts: list[str]) -> dict:
    name = item.get("name") or item.get("handle")
    handle = item.get("handle")
    site = item.get("site")
    listing = item.get("listing_at_display") or item.get("listing_at")
    raw = item.get("_listing_at_raw") or ""
    why = item.get("_why") or ""
    snippet = item.get("_x_progress_snippet") or ""
    joined = "\n".join(posts[:12])
    blob = f"{why}\n{snippet}\n{raw}\n{site_text}\n{joined}"

    play = []
    if why:
        play.append(why[:200])
    if re.search(r"mint|铸造|NFT", blob, re.I):
        play.append("涉及 NFT mint / 铸造（详见官推）")
    if re.search(r"token|TGE|\$[A-Z]{2,}", blob, re.I):
        play.append("涉及代币/TGE（CA 以官推公布为准，当前未在本摘要中填写 CA）")
    if re.search(r"game|GameFi|MMORPG|play", blob, re.I):
        play.append("含游戏/GameFi 玩法")
    if not play:
        play.append(f"{name} 即将开盘；玩法细节以官网与官推为准")

    req = []
    if re.search(r"whitelist|waitlist|白名单|allowlist", blob, re.I):
        req.append("可能需要 waitlist / 白名单（以官推为准）")
    if re.search(r"wallet|钱包|EVM|MetaMask", blob, re.I):
        req.append("需要兼容钱包（链别以官推为准）")
    if re.search(r"free\s*mint|免费", blob, re.I):
        req.append("存在免费 mint / 免费参与通道线索（勿把付费档当成免费）")
    if not req:
        req.append("参与门槛未在公开材料中完整列出，开盘前复查官推")

    steps = []
    if site:
        steps.append(f"打开官网 {site}")
    if item.get("tweet_url"):
        steps.append(f"关注官推 {item.get('tweet_url')}")
    if listing:
        steps.append(f"开盘时间 {listing}（Asia/Shanghai，来源已记录，勿自行改写）")
    if not steps:
        steps.append("等待官推给出具体参与入口")

    risks = [
        "未核实的合约地址请勿交互；本 playbook 不填写未公布 CA",
        "费用/配额以官推与官网实时文案为准，摘要可能过期",
        "只认官方 X 与官网，谨防仿盘",
    ]

    sources = []
    if item.get("listing_at_evidence_url"):
        sources.append({"label": "开盘时间证据", "url": item["listing_at_evidence_url"]})
    if site:
        sources.append({"label": "官网", "url": site})
    if item.get("tweet_url"):
        sources.append({"label": "官推主页", "url": item["tweet_url"]})

    summary = f"{name}（@{handle}）开盘 {listing or '时间见官推'}；" + "；".join(play[:2])
    return {
        "updated_at": iso(),
        "summary": summary[:280],
        "玩法": play[:8],
        "参与需求": req[:8],
        "步骤": steps[:8],
        "风险注意": risks[:8],
        "来源": sources[:8],
    }


def ai_playbook(item: dict, site_text: str, posts: list[str]) -> dict | None:
    handle = item.get("handle")
    name = item.get("name")
    prompt = f"""你是加密项目开盘玩法整理助手。根据材料用中文输出严格 JSON（不要 markdown 围栏），字段：
summary(string), 玩法(string[]), 参与需求(string[]), 步骤(string[]), 风险注意(string[]), 来源([{{"label","url"}}])。
硬性规则：绝不编造合约地址/CA；未公布的费用写成「未公布」；只基于材料；时区 Asia/Shanghai。
项目：{name} @{handle}
链字段(可能未知)：{item.get('chain')}
开盘：{item.get('listing_at_display') or item.get('listing_at')}
官网：{item.get('site')}
证据链：{item.get('listing_at_evidence_url')}
材料摘录：
---SITE---
{site_text[:2500]}
---X---
{chr(10).join(posts[:15])[:3500]}
---RAW---
{(item.get('_listing_at_raw') or '')[:500]}
{(item.get('_why') or '')[:400]}
"""
    out = call_ds(prompt)
    if not out:
        return None
    # extract JSON object
    m = re.search(r"\{[\s\S]*\}", out)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    # sanitize: strip any 0x contracts that look invented in summary fields? keep text but don't add CA field
    pb = {
        "updated_at": iso(),
        "summary": str(obj.get("summary") or "")[:400],
        "玩法": [str(x) for x in (obj.get("玩法") or [])][:10],
        "参与需求": [str(x) for x in (obj.get("参与需求") or [])][:10],
        "步骤": [str(x) for x in (obj.get("步骤") or [])][:10],
        "风险注意": [str(x) for x in (obj.get("风险注意") or [])][:10],
        "来源": [],
    }
    for s in obj.get("来源") or []:
        if isinstance(s, dict) and s.get("url"):
            pb["来源"].append({"label": str(s.get("label") or "来源"), "url": str(s["url"])})
    if item.get("listing_at_evidence_url") and not any(
        (s.get("url") == item["listing_at_evidence_url"]) for s in pb["来源"]
    ):
        pb["来源"].insert(0, {"label": "开盘时间证据", "url": item["listing_at_evidence_url"]})
    if item.get("site") and not any((s.get("url") == item["site"]) for s in pb["来源"]):
        pb["来源"].append({"label": "官网", "url": item["site"]})
    if not pb["玩法"]:
        return None
    return pb


def refresh_one(item: dict, *, force: bool = False, use_ds: bool = True) -> bool:
    if not needs_refresh(item.get("playbook"), force=force):
        return False
    site_text = fetch_site(item.get("site"))
    posts = x_posts_for(item.get("handle") or "")
    pb = None
    if use_ds and ds_available():
        pb = ai_playbook(item, site_text, posts)
    if not pb:
        pb = heuristic_playbook(item, site_text, posts)
    item["playbook"] = pb
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-ds", action="store_true")
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--only", nargs="*", help="Only these handles")
    args = ap.parse_args()
    doc = load(OUT, {})
    items = doc.get("items") or []
    if not items:
        print(json.dumps({"ok": False, "error": "no today_projects items"}, ensure_ascii=False))
        return 1
    only = {norm(h) for h in (args.only or [])} if args.only else None
    refreshed = []
    for it in items:
        if only and norm(it.get("handle")) not in only:
            continue
        if refresh_one(it, force=args.force, use_ds=not args.no_ds):
            refreshed.append(it.get("handle"))
    doc["generated_at"] = iso()
    save_doc(doc)
    summary = {"refreshed": refreshed, "count": len(items), "skipped": len(items) - len(refreshed)}
    if args.publish:
        try:
            from publish_pages_file import put_file, put_file_to_branch

            msg = f"data: today_projects playbook (count={len(items)})"
            summary["publish_main"] = put_file(OUT, "public/data/today_projects.json", message=msg)
            summary["publish_gh_pages"] = put_file_to_branch(
                OUT, "data/today_projects.json", "gh-pages", message=msg + " (gh-pages)"
            )
        except Exception as e:
            summary["publish_error"] = str(e)[:200]
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
