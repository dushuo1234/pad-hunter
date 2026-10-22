#!/usr/bin/env python3
"""Fetch Telegram 「项目推送」 messages and classify project cards.

Reads credentials from the environment or an untracked env file.
Never prints API hashes, proxy passwords, phone numbers, or session contents.
Local snapshots, jsonl logs, and Telethon sessions stay under TG_DATA_DIR
(default: scripts/telegram/.data) and must not be committed.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("TG_DATA_DIR", SCRIPT_DIR / ".data")).expanduser()
ENV_FILE = Path(os.environ.get("TG_ENV_FILE", SCRIPT_DIR / ".env")).expanduser()
SESSION = os.environ.get("TG_SESSION", str(DATA_DIR / "tg.session"))
TARGET_FILE = Path(os.environ.get("TG_TARGET_FILE", DATA_DIR / "target.json")).expanduser()
JSONL = DATA_DIR / "projects.jsonl"
SNAPSHOT = DATA_DIR / "projects.json"

ENV_KEYS = (
    "TG_API_ID",
    "TG_API_HASH",
    "TG_SESSION",
    "TG_PEER",
    "TG_TARGET_FILE",
    "TG_PROXY_TYPE",
    "TG_PROXY_HOST",
    "TG_PROXY_PORT",
    "TG_PROXY_USER",
    "TG_PROXY_PASS",
)

SHANGHAI = ZoneInfo("Asia/Shanghai")

# Project card must start with 🆕 and have chain line
CARD_START = re.compile(r"^🆕\s*(.+?)\s*\(@([A-Za-z0-9_]+)\)\s*$", re.M)
CHAIN_LINE = re.compile(r"^⛓\s*(.+?)\s*[·•]\s*(.+?)\s*$", re.M)
BLURB_LINE = re.compile(r"^📝\s*(.+)$", re.M)
FANS_LINE = re.compile(r"^👥\s*(.+)$", re.M)
CN_SUMMARY = re.compile(r"^🤖\s*(.+)$", re.M)
STATUS_LINE = re.compile(r"^[⏰🔨🔥✅❌🚀]\s*状态[:：]\s*(.+)$", re.M)
# also allow plain "状态:"
STATUS_LINE2 = re.compile(r"状态[:：]\s*(.+)$", re.M)
LISTING_LINE = re.compile(r"^🔒\s*开盘[:：]\s*(.+)$", re.M)
LISTING_LINE2 = re.compile(r"开盘[:：]\s*(.+)$", re.M)
RISK_LINE = re.compile(r"^⚠️\s*风险[:：]\s*(.+)$", re.M)
RISK_LINE2 = re.compile(r"风险[:：]\s*(.+)$", re.M)
LINK_LINE = re.compile(r"^🔗\s*(https?://\S+)\s*$", re.M)
URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
X_URL = re.compile(r"https?://(?:x\.com|twitter\.com)/[A-Za-z0-9_]+/?", re.I)


def load_env() -> Dict[str, str]:
    """Merge an optional env file with the process environment. Env wins."""
    cfg: Dict[str, str] = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip().strip('"').strip("'")
    for key in ENV_KEYS:
        if os.environ.get(key):
            cfg[key] = os.environ[key]
    return cfg


def scrub_err(msg: str, secrets: Optional[List[str]] = None) -> str:
    msg = msg[:400]
    msg = re.sub(
        r"(password|hash|api[_-]?hash|proxy.?pass|phone)[=:].*",
        r"\1=REDACTED",
        msg,
        flags=re.I,
    )
    for secret in secrets or []:
        if secret and len(secret) >= 4:
            msg = msg.replace(secret, "REDACTED")
    return msg


def first_match(pat: re.Pattern, text: str) -> Optional[str]:
    m = pat.search(text)
    return m.group(1).strip() if m else None


def parse_card(text: str, message_id: int, date_iso: Optional[str], urls: List[str]) -> Optional[Dict[str, Any]]:
    if not text or "🆕" not in text:
        return None
    m = CARD_START.search(text)
    if not m:
        return None
    name = m.group(1).strip()
    handle = m.group(2).strip()

    chain_m = CHAIN_LINE.search(text)
    if not chain_m:
        # not a structured project card
        return None
    chain = chain_m.group(1).strip()
    category = chain_m.group(2).strip()

    blurb = first_match(BLURB_LINE, text) or ""
    fans = first_match(FANS_LINE, text) or ""
    summary_cn = first_match(CN_SUMMARY, text) or ""
    # English blurb is the 📝 line
    summary_en = blurb

    status = first_match(STATUS_LINE, text) or first_match(STATUS_LINE2, text) or ""
    listing = first_match(LISTING_LINE, text) or first_match(LISTING_LINE2, text) or ""
    risk = first_match(RISK_LINE, text) or first_match(RISK_LINE2, text) or ""

    found_urls = list(dict.fromkeys(URL_RE.findall(text) + (urls or [])))
    # prefer explicit 🔗 line
    link_m = LINK_LINE.search(text)
    if link_m and link_m.group(1) not in found_urls:
        found_urls.insert(0, link_m.group(1))

    x_links = [u for u in found_urls if X_URL.match(u)]
    if not x_links and handle:
        x_links = [f"https://x.com/{handle}"]

    return {
        "message_id": message_id,
        "date_iso": date_iso,
        "name": name,
        "twitter_handle": handle,
        "chain": chain,
        "category": category,
        "status": status,
        "listing": listing,
        "risk": risk,
        "urls": found_urls,
        "x_url": x_links[0] if x_links else "",
        "fans": fans,
        "summary_cn": summary_cn,
        "summary_en": summary_en,
        "raw_text": text,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def load_jsonl() -> Dict[int, Dict[str, Any]]:
    by_id: Dict[int, Dict[str, Any]] = {}
    if not JSONL.exists():
        return by_id
    for line in JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            mid = int(obj["message_id"])
            by_id[mid] = obj
        except Exception:
            continue
    return by_id


def write_jsonl(by_id: Dict[int, Dict[str, Any]]) -> None:
    # rewrite sorted by message_id desc for readability
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    items = sorted(by_id.values(), key=lambda x: int(x.get("message_id", 0)), reverse=True)
    with JSONL.open("w", encoding="utf-8") as f:
        for obj in items:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
    os.chmod(JSONL, 0o600)


def write_snapshot(by_id: Dict[int, Dict[str, Any]]) -> List[Dict[str, Any]]:
    # unique by twitter_handle (prefer newest message_id) and keep the earliest card time
    from push_date import collapse_by_handle

    slim = collapse_by_handle(by_id.values())
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(slim, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(SNAPSHOT, 0o600)
    return slim


def to_shanghai(date_iso: Optional[str]) -> str:
    if not date_iso:
        return ""
    try:
        dt = datetime.fromisoformat(date_iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(SHANGHAI).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return date_iso


def write_board_md(projects: List[Dict[str, Any]], path: Path) -> None:
    lines = [
        "# 项目推送 · 分类看板",
        "",
        f"更新时间（Asia/Shanghai）：{datetime.now(SHANGHAI).strftime('%Y-%m-%d %H:%M:%S')}",
        f"项目数：{len(projects)}",
        "",
        "| 项目名 | 链 | 类型/发射台 | 状态 | 开盘 | X链接 | 时间(Asia/Shanghai) |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in projects:
        name = (p.get("name") or "").replace("|", "\\|")
        handle = p.get("twitter_handle") or ""
        title = f"{name}" + (f" (@{handle})" if handle else "")
        chain = (p.get("chain") or "").replace("|", "\\|")
        cat = (p.get("category") or "").replace("|", "\\|")
        status = (p.get("status") or "").replace("|", "\\|")
        listing = (p.get("listing") or "").replace("|", "\\|")
        xurl = p.get("x_url") or ""
        xcell = f"[链接]({xurl})" if xurl else ""
        t = to_shanghai(p.get("date_iso"))
        lines.append(f"| {title} | {chain} | {cat} | {status} | {listing} | {xcell} | {t} |")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_board_html(projects: List[Dict[str, Any]], path: Path) -> None:
    # embed data as JSON
    data = []
    for p in projects:
        data.append({
            "name": p.get("name") or "",
            "handle": p.get("twitter_handle") or "",
            "chain": p.get("chain") or "",
            "category": p.get("category") or "",
            "status": p.get("status") or "",
            "listing": p.get("listing") or "",
            "x_url": p.get("x_url") or "",
            "summary_cn": p.get("summary_cn") or "",
            "summary_en": p.get("summary_en") or "",
            "risk": p.get("risk") or "",
            "time": to_shanghai(p.get("date_iso")),
            "message_id": p.get("message_id"),
        })
    payload = json.dumps(data, ensure_ascii=False)
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>项目推送 · AlphaRadar 风格看板</title>
<style>
  :root {{
    --bg: #0b0f14; --panel: #121821; --border: #1e2a38; --text: #e7eef7;
    --muted: #8b9bb0; --accent: #3dd68c; --chip: #1a2430; --hover: #182231;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "PingFang SC", "Noto Sans SC", sans-serif;
    background: radial-gradient(1200px 600px at 10% -10%, #122033 0%, transparent 60%), var(--bg);
    color: var(--text); min-height: 100vh;
  }}
  header {{
    padding: 20px 24px 8px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center; justify-content: space-between;
  }}
  h1 {{ margin: 0; font-size: 20px; letter-spacing: 0.2px; }}
  h1 span {{ color: var(--accent); }}
  .meta {{ color: var(--muted); font-size: 13px; }}
  .toolbar {{
    padding: 8px 24px 16px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center;
  }}
  input, select {{
    background: var(--panel); color: var(--text); border: 1px solid var(--border);
    border-radius: 10px; padding: 9px 12px; font-size: 13px; outline: none;
  }}
  input {{ min-width: 220px; flex: 1; }}
  select {{ min-width: 140px; }}
  input:focus, select:focus {{ border-color: #2f6fed; }}
  .chips {{ display: flex; flex-wrap: wrap; gap: 6px; padding: 0 24px 8px; }}
  .chip {{
    background: var(--chip); border: 1px solid var(--border); color: var(--muted);
    border-radius: 999px; padding: 4px 10px; font-size: 12px;
  }}
  .chip b {{ color: var(--text); font-weight: 600; }}
  main {{ padding: 0 16px 40px; }}
  table {{
    width: 100%; border-collapse: separate; border-spacing: 0;
    background: var(--panel); border: 1px solid var(--border); border-radius: 14px; overflow: hidden;
  }}
  th, td {{ padding: 11px 12px; text-align: left; border-bottom: 1px solid var(--border); vertical-align: top; font-size: 13px; }}
  th {{ color: var(--muted); font-weight: 600; background: #0f1520; position: sticky; top: 0; }}
  tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover {{ background: var(--hover); }}
  .name {{ font-weight: 600; }}
  .handle {{ color: var(--muted); font-size: 12px; }}
  .tag {{
    display: inline-block; background: #152033; border: 1px solid #243447; border-radius: 8px;
    padding: 2px 8px; font-size: 12px; white-space: nowrap;
  }}
  .tag.chain {{ color: #7ec8ff; }}
  .tag.cat {{ color: #ffd27a; }}
  a {{ color: #6ea8fe; text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .empty {{ padding: 40px; text-align: center; color: var(--muted); }}
  .sum {{ color: var(--muted); font-size: 12px; max-width: 360px; line-height: 1.45; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>项目推送 <span>· Radar</span></h1>
    <div class="meta" id="meta"></div>
  </div>
</header>
<div class="toolbar">
  <input id="q" type="search" placeholder="搜索项目名 / 链 / 类型 / 状态…"/>
  <select id="chain"><option value="">全部链</option></select>
  <select id="cat"><option value="">全部类型</option></select>
</div>
<div class="chips" id="stats"></div>
<main>
  <table>
    <thead>
      <tr>
        <th>项目</th><th>链</th><th>类型</th><th>状态</th><th>开盘</th><th>X</th><th>时间</th><th>摘要</th>
      </tr>
    </thead>
    <tbody id="tbody"></tbody>
  </table>
  <div class="empty" id="empty" style="display:none">没有匹配的项目</div>
</main>
<script>
const DATA = {payload};
const meta = document.getElementById('meta');
const tbody = document.getElementById('tbody');
const empty = document.getElementById('empty');
const q = document.getElementById('q');
const chainSel = document.getElementById('chain');
const catSel = document.getElementById('cat');
const stats = document.getElementById('stats');

meta.textContent = '共 ' + DATA.length + ' 个项目 · 本地静态看板 · Asia/Shanghai';

function uniq(key) {{
  const m = new Map();
  for (const p of DATA) {{
    const v = (p[key] || '未知').trim() || '未知';
    m.set(v, (m.get(v) || 0) + 1);
  }}
  return [...m.entries()].sort((a,b)=>b[1]-a[1]);
}}
for (const [v] of uniq('chain')) {{
  const o = document.createElement('option'); o.value = v; o.textContent = v; chainSel.appendChild(o);
}}
for (const [v] of uniq('category')) {{
  const o = document.createElement('option'); o.value = v; o.textContent = v; catSel.appendChild(o);
}}
function renderStats() {{
  const chains = uniq('chain').slice(0, 8);
  const cats = uniq('category').slice(0, 8);
  stats.innerHTML = '';
  for (const [k,c] of chains) {{
    const d = document.createElement('div'); d.className='chip'; d.innerHTML = '链 <b>'+k+'</b> '+c; stats.appendChild(d);
  }}
  for (const [k,c] of cats) {{
    const d = document.createElement('div'); d.className='chip'; d.innerHTML = '类型 <b>'+k+'</b> '+c; stats.appendChild(d);
  }}
}}
function esc(s) {{
  return String(s||'').replace(/[&<>"']/g, c => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
}}
function filtered() {{
  const qq = q.value.trim().toLowerCase();
  const ch = chainSel.value;
  const ca = catSel.value;
  return DATA.filter(p => {{
    if (ch && (p.chain||'') !== ch) return false;
    if (ca && (p.category||'') !== ca) return false;
    if (!qq) return true;
    const blob = [p.name,p.handle,p.chain,p.category,p.status,p.listing,p.summary_cn,p.summary_en].join(' ').toLowerCase();
    return blob.includes(qq);
  }});
}}
function render() {{
  const rows = filtered();
  tbody.innerHTML = '';
  empty.style.display = rows.length ? 'none' : 'block';
  for (const p of rows) {{
    const tr = document.createElement('tr');
    const x = p.x_url ? '<a href="'+esc(p.x_url)+'" target="_blank" rel="noopener">@'+esc(p.handle||'x')+'</a>' : '-';
    tr.innerHTML = `
      <td><div class="name">${{esc(p.name)}}</div><div class="handle">@${{esc(p.handle)}}</div></td>
      <td><span class="tag chain">${{esc(p.chain)}}</span></td>
      <td><span class="tag cat">${{esc(p.category)}}</span></td>
      <td>${{esc(p.status)}}</td>
      <td>${{esc(p.listing)}}</td>
      <td>${{x}}</td>
      <td>${{esc(p.time)}}</td>
      <td><div class="sum">${{esc(p.summary_cn || p.summary_en)}}</div></td>`;
    tbody.appendChild(tr);
  }}
}}
q.addEventListener('input', render);
chainSel.addEventListener('change', render);
catSel.addEventListener('change', render);
renderStats();
render();
</script>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def resolve_peer(cfg: Dict[str, str]) -> Any:
    raw = (cfg.get("TG_PEER") or "").strip()
    if raw:
        if raw.lstrip("-").isdigit():
            return int(raw)
        return raw
    if TARGET_FILE.exists():
        target = json.loads(TARGET_FILE.read_text(encoding="utf-8"))
        peer = target.get("peer_id") or target.get("id") or target.get("username")
        if peer is not None and peer != "":
            return peer
    raise RuntimeError("set TG_PEER or TG_TARGET_FILE")


async def fetch_messages(limit: int) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Returns (raw message dicts, error_or_none). Never prints secrets."""
    cfg = load_env()
    secrets = [cfg.get("TG_API_HASH", ""), cfg.get("TG_PROXY_PASS", ""), cfg.get("TG_PROXY_USER", "")]
    if not cfg.get("TG_API_ID") or not cfg.get("TG_API_HASH"):
        return [], "missing TG_API_ID or TG_API_HASH"
    try:
        api_id = int(cfg["TG_API_ID"])
    except ValueError:
        return [], "TG_API_ID must be an integer"
    api_hash = cfg["TG_API_HASH"]
    try:
        peer = resolve_peer(cfg)
    except Exception as e:
        return [], scrub_err(str(e), secrets)

    proxy = None
    if cfg.get("TG_PROXY_HOST") and cfg.get("TG_PROXY_PORT"):
        ptype = cfg.get("TG_PROXY_TYPE", "http").lower()
        try:
            port = int(cfg["TG_PROXY_PORT"])
        except ValueError:
            return [], "TG_PROXY_PORT must be an integer"
        proxy = (
            ptype,
            cfg["TG_PROXY_HOST"],
            port,
            True,
            cfg.get("TG_PROXY_USER") or None,
            cfg.get("TG_PROXY_PASS") or None,
        )

    from telethon import TelegramClient

    kwargs = dict(
        proxy=proxy,
        connection_retries=40,
        retry_delay=2,
        timeout=45,
        request_retries=8,
    )
    client = TelegramClient(SESSION, api_id, api_hash, **kwargs)
    msgs: List[Dict[str, Any]] = []
    err: Optional[str] = None
    try:
        await client.connect()
        if not await client.is_user_authorized():
            return [], "session not authorized"
        entity = await client.get_entity(peer)
        async for m in client.iter_messages(entity, limit=limit):
            text = m.message or m.text or ""
            urls = URL_RE.findall(text) if text else []
            date_iso = m.date.isoformat() if m.date else None
            msgs.append({
                "id": m.id,
                "date": date_iso,
                "text": text,
                "urls": list(dict.fromkeys(urls)),
            })
    except Exception as e:
        err = f"{type(e).__name__}: {scrub_err(str(e), secrets)}"
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass
    return msgs, err


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch & classify 项目推送 cards")
    ap.add_argument("limit", nargs="?", type=int, default=50, help="latest N messages (default 50)")
    ap.add_argument("--offline", action="store_true", help="classify from a local sample JSON only")
    ap.add_argument("--sample", default=str(SCRIPT_DIR / "fixtures" / "sample_messages.json"))
    ap.add_argument("--board-md", default=str(DATA_DIR / "board.md"))
    ap.add_argument("--board-html", default=str(DATA_DIR / "board.html"))
    args = ap.parse_args()

    error = None
    raw: List[Dict[str, Any]] = []
    if args.offline:
        sample = Path(args.sample)
        raw = json.loads(sample.read_text(encoding="utf-8"))
        print(f"fetched: {len(raw)} (offline sample)")
    else:
        raw, error = asyncio.run(fetch_messages(args.limit))
        print(f"fetched: {len(raw)}")
        if error:
            print(f"error: {error}")

    existing = load_jsonl()
    new_count = 0
    updated_count = 0
    parsed_this_run: List[Dict[str, Any]] = []

    for m in raw:
        text = m.get("text") or ""
        card = parse_card(text, int(m["id"]), m.get("date"), m.get("urls") or [])
        if not card:
            continue
        mid = card["message_id"]
        parsed_this_run.append(card)
        if mid in existing:
            # update fields but keep first fetched_at if present
            old = existing[mid]
            card["fetched_at"] = old.get("fetched_at") or card["fetched_at"]
            if old != card:
                updated_count += 1
            existing[mid] = card
        else:
            existing[mid] = card
            new_count += 1

    write_jsonl(existing)
    snapshot = write_snapshot(existing)

    # Prefer this-run cards for board if we got any; else full snapshot
    board_src = parsed_this_run if parsed_this_run else snapshot
    # de-dupe board by handle preferring higher message_id
    by_h: Dict[str, Dict[str, Any]] = {}
    for o in sorted(board_src, key=lambda x: int(x.get("message_id", 0))):
        h = (o.get("twitter_handle") or "").lower() or f"msg:{o.get('message_id')}"
        by_h[h] = o
    board_projects = sorted(by_h.values(), key=lambda x: int(x.get("message_id", 0)), reverse=True)

    md_path = Path(args.board_md)
    html_path = Path(args.board_html)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    write_board_md(board_projects, md_path)
    write_board_html(board_projects, html_path)

    # counts
    from collections import Counter
    chains = Counter((p.get("chain") or "未知") for p in board_projects)
    cats = Counter((p.get("category") or "未知") for p in board_projects)

    print(f"project_cards_parsed: {len(parsed_this_run)}")
    print(f"new: {new_count}")
    print(f"updated: {updated_count}")
    print(f"snapshot_unique: {len(snapshot)}")
    print(f"board_rows: {len(board_projects)}")
    print("top_chains: " + ", ".join(f"{k}={v}" for k, v in chains.most_common(8)))
    print("top_categories: " + ", ".join(f"{k}={v}" for k, v in cats.most_common(8)))
    print(f"jsonl: {JSONL}")
    print(f"snapshot: {SNAPSHOT}")
    print(f"board_md: {md_path}")
    print(f"board_html: {html_path}")
    if error and not parsed_this_run:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
