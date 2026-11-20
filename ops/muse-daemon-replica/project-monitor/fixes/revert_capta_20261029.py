#!/usr/bin/env python3
"""Revert wrong 固定CA/已开盘 for Capta (@captadotdl) CA 0x8b50…95f3 (2026-10-29)."""
import json, sys, os, fcntl
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
BASE = Path("/workspace/project-monitor"); sys.path.insert(0, str(BASE))
TZ = ZoneInfo("Asia/Shanghai"); NOW = datetime.now(TZ).isoformat(timespec="seconds")
H = "captadotdl"; CA = "0x8b50c3137680e1b179a1767b2c8bf79e8b7e95f3"
REASON = "REVOKED 2026-10-29: @captadotdl is a founder/KOL account (not project official); CA is SQUEEK/SQK honeypot/copycat (fake @squeekchain coin)."
KOL_RISK = "个人号/KOL，非项目官推；2026-10-29 推文中的 0x8b50…95f3 为 SQUEEK/SQK 蜜罐/假币，已撤销固定CA"
out = {}

def lj(p, d=None):
    try: return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception: return d
def dj(p, o):
    p = Path(p); t = p.with_suffix(p.suffix + ".tmp")
    t.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"); t.replace(p)

# 1) ca_project_lock
lp = BASE / "ca_project_lock.json"
with lp.open("r+") as lf:
    fcntl.flock(lf, fcntl.LOCK_EX)
    d = json.loads(lp.read_text(encoding="utf-8"))
    ent = (d.get("projects") or {}).pop(H, None)
    d.setdefault("revoked", {})[H] = {**(ent or {}), "revoked_at": NOW, "revoked_reason": REASON}
    d["updated_at"] = NOW
    dj(lp, d); fcntl.flock(lf, fcntl.LOCK_UN)
out["ca_lock_removed"] = bool(ent)

# 2) removed_launched → restored
rp = BASE / "removed_launched.json"; d = lj(rp)
n = 0
for e in d.get("items") or []:
    if (e.get("handle") or "").lower() == H and not e.get("restored"):
        e.update({"restored": True, "restored_at": NOW, "revoked": True, "revoked_reason": REASON,
                  "ca_status": "suspected_copycat"}); n += 1
dj(rp, d); out["removed_launched_restored"] = n

# 3) T-20 state: keep stopped (KOL, no more watching) but mark revoked, clear last_ca
sp = BASE / "alerts" / "today_t20_state.json"; d = lj(sp)
hs = (d.get("handles") or {}).get(H)
if hs is not None:
    hs.update({"stopped": True, "stop_reason": "kol_not_official_revoked", "revoked_ca": hs.pop("last_ca", None),
               "revoked_at": NOW})
dj(sp, d); out["t20_state"] = bool(hs)

# 4) annotate alert jsonl rows (same inode rewrite)
for name in ("alerts/today_t20_alerts.jsonl", "alerts/workbench_soon.jsonl", "alerts/today_t20_wake_queue.jsonl"):
    p = BASE / name; lines = p.read_text(encoding="utf-8").splitlines(keepends=True); cnt = 0
    for i, ln in enumerate(lines):
        if CA in ln.lower() and H in ln.lower():
            try: r = json.loads(ln)
            except Exception: continue
            r.update({"revoked": True, "revoked_at": NOW, "ca_status": "suspected_copycat", "ca_fixed": False,
                      "confidence": "revoked", "revoked_reason": REASON})
            lines[i] = json.dumps(r, ensure_ascii=False) + "\n"; cnt += 1
    with p.open("r+", encoding="utf-8") as f:
        f.seek(0); f.write("".join(lines)); f.truncate()
    out[name] = cnt

# 5) pending msg files → empty; history → append revoke note; wake file → .revoked
for name in ("_today_t20_highconf_msg.txt", "_today_t20_launched_msg.txt", "_today_t20_latest_fixed.txt"):
    p = BASE / name
    if p.exists() and H in p.read_text(encoding="utf-8"):
        p.write_text("", encoding="utf-8"); out[name] = "cleared"
for name in ("_today_t20_highconf_history.txt", "_today_t20_launched_history.txt"):
    p = BASE / name
    with p.open("a", encoding="utf-8") as f:
        f.write(f"\n\n❌ 撤销 · Capta（@captadotdl）CA `{CA}` · {NOW} Asia/Shanghai\n- {REASON}\n")
wf = BASE / "alerts" / "today_t20_wake" / f"{H}.txt"
if wf.exists(): wf.rename(wf.with_suffix(".txt.revoked")); out["wake_file"] = "renamed .revoked"

# 6) restore Capta as a KOL card (no CA, no listing, not 已开盘) into candidates/projects/tg-monitor
snap = None
for e in lj(rp).get("items") or []:
    if (e.get("handle") or "").lower() == H: snap = e.get("snapshot") or {}
cp = Path("/workspace/push-radar/data/candidates.json"); cd = lj(cp)
cands = cd["candidates"]
if not any((c.get("handle") or "").lower() == H for c in cands):
    cands.append({"name": "Capta", "handle": "captadotdl", "chain": "未知", "category": "其他", "status": "不明",
                  "listing": "未提及", "listing_at": None, "listing_at_display": "未知", "already_listed": False,
                  "within_next_3_days": False, "risk": KOL_RISK, "site": None, "tweet_url": "https://x.com/captadotdl",
                  "followers": 18130, "kol_followers": None,
                  "bio": "Founder @ArcadyWeb3 @ForbesWeb3 @theNextDAO", "why": "创始人/KOL 个人号（非项目）",
                  "notes": "2026-10-29 撤销误判固定CA/已开盘", "ca": None, "ca_status": None,
                  "rank": len(cands) + 1, "score": None, "source": "telegram:青年大学习",
                  "message_id": snap.get("message_id") if snap else None,
                  "date_iso": (snap or {}).get("date_iso"), "push_date": (snap or {}).get("date_iso")})
    for i, c in enumerate(cands, 1): c["rank"] = i
    cd["updated_at"] = NOW; dj(cp, cd); out["candidates"] = "restored KOL card"
pp = Path("/workspace/push-radar/data/projects.json"); pj = lj(pp)
if not any((x.get("twitter_handle") or x.get("handle") or "").lower() == H for x in pj):
    pj.append({"message_id": (snap or {}).get("message_id"), "date_iso": (snap or {}).get("date_iso"), "name": "Capta",
               "twitter_handle": "captadotdl", "chain": "未知", "category": "其他", "status": "不明", "listing": "未提及",
               "risk": KOL_RISK, "urls": ["https://x.com/captadotdl"], "x_url": "https://x.com/captadotdl",
               "fans": (snap or {}).get("fans"), "summary_cn": "Capta：创始人/KOL 个人号（Founder @ArcadyWeb3），非项目官推；不发 CA。",
               "summary_en": "", "source_channel": "青年大学习"})
    dj(pp, pj); out["projects"] = "restored KOL card"
tp = Path("/home/box/.tg-monitor/projects.json"); td = lj(tp)
rows = td if isinstance(td, list) else (td.get("projects") or td.get("items") or [])
for x in rows:
    if (x.get("twitter_handle") or "").lower() == H:
        x.update({"risk": KOL_RISK, "category": "其他", "status": "不明",
                  "summary_cn": "Capta：创始人/KOL 个人号（Founder @ArcadyWeb3），非项目官推；不发 CA。"})
        out["tg_monitor"] = "risk→KOL"
dj(tp, td)

# 7) today list: make sure not present
tdp = BASE / "today_projects.json"; t = lj(tdp)
before = len(t.get("items") or []); t["items"] = [i for i in t.get("items") or [] if (i.get("handle") or "").lower() != H]
t["count"] = len(t["items"]); dj(tdp, t); out["today_dropped"] = before - len(t["items"])
print(json.dumps(out, ensure_ascii=False, indent=1))
