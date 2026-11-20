#!/usr/bin/env python3
"""Ingest @TapeRobot_bsc posts (x MCP get_users_posts output file) → extract 0x addresses → push.

Usage (routine, every ~5 min):
  1) x get_users_posts id=3114058692 since_id=<tapeout_x_state.json.since_id> max_results=10
     post.fields=created_at,entities,note_tweet  (write_to_file)
  2) python3 tapeout_x_ingest.py <that file>
Prints NEW_TAPEOUT_CA lines for any address that won the push (first source wins), else QUIET.
Only the account's own text/URLs are parsed; addresses still must pass ca_gate (token or NFT/1155).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
sys.path.insert(0, str(BASE))
from tapeout_push import push_candidate  # noqa: E402

STATE = BASE / "tapeout_x_state.json"
LOG = BASE / "tapeout_x_posts.jsonl"
USER_ID = "3114058692"
HANDLE = "TapeRobot_bsc"
EVM = re.compile(r"0x[a-fA-F0-9]{40}(?![a-fA-F0-9])")
SH = ZoneInfo("Asia/Shanghai")


def parse(path: str) -> dict:
    t = Path(path).read_text(encoding="utf-8", errors="replace")
    i = t.find("{")
    return json.JSONDecoder().raw_decode(t[i:])[0] if i >= 0 else {}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__); return 2
    d = parse(sys.argv[1])
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    posts = d.get("data") or []
    since = int(st.get("since_id") or 0)
    hits = []
    for p in sorted(posts, key=lambda x: int(x["id"])):
        pid = int(p["id"])
        txt = ((p.get("note_tweet") or {}).get("text") or p.get("text") or "")
        urls = [u.get("expanded_url") or "" for u in ((p.get("entities") or {}).get("urls") or [])]
        blob = txt + "\n" + "\n".join(urls)
        addrs = sorted({a for a in EVM.findall(blob)}, key=str.lower)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(SH).isoformat(timespec="seconds"), "id": p["id"],
                                "created_at": p.get("created_at"), "addresses": addrs, "text": txt[:400]},
                               ensure_ascii=False) + "\n")
        for a in addrs:
            url = f"https://x.com/{HANDLE}/status/{p['id']}"
            ev = push_candidate(a, source=f"x:@{HANDLE}", meta={"post_url": url, "post_text": txt[:200],
                                                                "post_created_at": p.get("created_at")})
            if ev:
                hits.append(ev)
        since = max(since, pid)
    if posts:
        st["since_id"] = str(since)
    st["last_run_at"] = datetime.now(SH).isoformat(timespec="seconds")
    st["user_id"] = USER_ID
    STATE.write_text(json.dumps(st, indent=2) + "\n")
    for ev in hits:
        print("NEW_TAPEOUT_CA", ev["alert_zh"])
    if not hits:
        print(f"QUIET posts={len(posts)} since_id={st.get('since_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
