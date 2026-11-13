#!/usr/bin/env python3
"""Push 今日项目清单 digest to Telegram group. Dedupes by content hash per calendar day unless --force."""
from __future__ import annotations
import argparse, hashlib, json, urllib.parse, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
BASE = Path(__file__).resolve().parent
TZ = ZoneInfo("Asia/Shanghai")
TOKEN_FILE = BASE / "secrets" / "telegram_bot_token"
CHAT_FILE = BASE / "secrets" / "telegram_today_chat.json"
TODAY = BASE / "today_projects.json"
STATE = BASE / "alerts" / "today_projects_tg_state.json"

def load_json(p, d=None):
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return d if d is not None else {}

def token() -> str:
    return TOKEN_FILE.read_text(encoding="utf-8").strip()

def chat_id() -> int:
    return int(load_json(CHAT_FILE, {})["chat_id"])

def items_fingerprint(doc: dict) -> str:
    """Stable hash body: ignore wall-clock so same-day unchanged list does not re-push."""
    rows = []
    for it in doc.get("items") or []:
        if not isinstance(it, dict):
            continue
        summ = ((it.get("playbook") or {}).get("summary") or "").strip()[:160]
        rows.append("|".join([
            str(it.get("handle") or ""),
            str(it.get("name") or ""),
            str(it.get("listing_at_display") or it.get("listing_at") or ""),
            str(it.get("chain") or ""),
            summ,
            str(it.get("site") or ""),
        ]))
    return "\n".join(rows)

def build_text(doc: dict) -> str:
    now = datetime.now(TZ)
    lines = [f"📋 <b>今日项目清单</b>（{now.strftime('%m-%d %H:%M')} Asia/Shanghai）", ""]
    items = doc.get("items") or []
    if not items:
        lines.append("（暂无 48 小时内有具体开盘时间的项目）")
    for it in items:
        name = it.get("name") or it.get("handle")
        h = it.get("handle") or ""
        la = it.get("listing_at_display") or it.get("listing_at") or "?"
        chain = it.get("chain") or ""
        summ = ((it.get("playbook") or {}).get("summary") or "").strip()
        site = it.get("site") or ""
        lines.append(f"• <b>{name}</b> @{h}")
        lines.append(f"  开盘：{la}" + (f" · {chain}" if chain else ""))
        if summ: lines.append(f"  {summ[:160]}")
        if site: lines.append(f"  {site}")
        lines.append("")
    return "\n".join(lines).strip()

def send(text: str) -> dict:
    body = urllib.parse.urlencode({
        "chat_id": chat_id(),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token()}/sendMessage", data=body, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    doc = load_json(TODAY, {"items": []})
    text = build_text(doc)
    day = datetime.now(TZ).strftime("%Y-%m-%d")
    h = hashlib.sha256(items_fingerprint(doc).encode()).hexdigest()[:16]
    st = load_json(STATE, {})
    if not args.force and st.get("day") == day and st.get("hash") == h:
        print(json.dumps({"ok": True, "skipped": "unchanged", "day": day, "count": len(doc.get("items") or [])}, ensure_ascii=False))
        return 0
    if args.dry_run:
        print(text)
        return 0
    res = send(text)
    ok = bool(res.get("ok"))
    STATE.parent.mkdir(parents=True, exist_ok=True)
    if ok:
        mid = ((res.get("result") or {}).get("message_id"))
        STATE.write_text(json.dumps({"day": day, "hash": h, "at": datetime.now(TZ).isoformat(timespec="seconds"), "message_id": mid, "count": len(doc.get("items") or [])}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"ok": ok, "count": len(doc.get("items") or []), "message_id": (res.get("result") or {}).get("message_id")}, ensure_ascii=False))
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
