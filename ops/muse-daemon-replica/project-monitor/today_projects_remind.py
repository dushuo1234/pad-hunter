#!/usr/bin/env python3
"""今日项目清单 · 开盘前 2 小时提醒。

对 listing_at ∈ (now, now+2h] 且 remind_2h_sent_at 为空的项目：
  - 追加 alerts/today_projects_remind.jsonl
  - 写回 remind_2h_sent_at
  - 打印中文消息到 stdout，并写 _today_remind_msg.txt
无待提醒时：静默 exit 0，消息文件写空。
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
OUT = BASE / "today_projects.json"
ALERTS = BASE / "alerts" / "today_projects_remind.jsonl"
MSG = BASE / "_today_remind_msg.txt"
MIRRORS = [
    Path("/workspace/push-radar/data/today_projects.json"),
    Path("/workspace/publish-pages-data/today_projects.json"),
]
TZ = ZoneInfo("Asia/Shanghai")


def now() -> datetime:
    return datetime.now(TZ)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).astimezone(TZ).isoformat(timespec="seconds")


def parse_dt(val) -> datetime | None:
    if not val:
        return None
    try:
        dt = datetime.fromisoformat(str(val).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except Exception:
        return None


def load_doc() -> dict:
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}


def save_doc(doc: dict) -> None:
    OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for dest in MIRRORS:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(OUT, dest)
        except OSError:
            pass


def format_msg(it: dict) -> str:
    pb = it.get("playbook") or {}
    summary = (pb.get("summary") or "").strip() or "玩法方案待补全"
    lines = [
        f"⏰ 开盘前2小时提醒 · medium · {it.get('name')}（@{it.get('handle')}）",
        f"- 开盘：{it.get('listing_at_display') or it.get('listing_at')}（Asia/Shanghai）",
        f"- 链：{it.get('chain') or '未知'} · 类目：{it.get('category') or '—'}",
    ]
    if it.get("site"):
        lines.append(f"- 官网：{it['site']}")
    if it.get("tweet_url"):
        lines.append(f"- 官推：{it['tweet_url']}")
    if it.get("listing_at_evidence_url"):
        lines.append(f"- 时间证据：{it['listing_at_evidence_url']}")
    lines.append(f"- 玩法摘要：{summary[:220]}")
    return "\n".join(lines)


def main() -> int:
    ref = now()
    end = ref + timedelta(hours=2)
    doc = load_doc()
    items = doc.get("items") or []
    due = []
    for it in items:
        if it.get("remind_2h_sent_at"):
            continue
        dt = parse_dt(it.get("listing_at"))
        if not dt:
            continue
        if ref < dt <= end:
            due.append(it)

    if not due:
        MSG.write_text("", encoding="utf-8")
        print("", end="")
        return 0

    ALERTS.parent.mkdir(parents=True, exist_ok=True)
    bodies = []
    ts = iso(ref)
    with ALERTS.open("a", encoding="utf-8") as f:
        for it in due:
            body = format_msg(it)
            bodies.append(body)
            rec = {
                "ts": ts,
                "kind": "today_projects_remind_2h",
                "handle": it.get("handle"),
                "name": it.get("name"),
                "listing_at": it.get("listing_at"),
                "listing_at_display": it.get("listing_at_display"),
                "site": it.get("site"),
                "tweet_url": it.get("tweet_url"),
                "message": body,
            }
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            it["remind_2h_sent_at"] = ts

    save_doc(doc)
    text = "\n\n".join(bodies) + "\n"
    MSG.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
