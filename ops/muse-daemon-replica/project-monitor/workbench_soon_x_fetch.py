#!/usr/bin/env python3
"""Workbench 官推 X 拉取：内置 X 日额度用完后自动切 6551，结果写入同一 x_inbox 形状。

State: alerts/x_quota_fallback.json
  {mode: "x"|"6551", since, reason, reset_hint, last_fetch_at, last_fetch,
   rr_offset, last_error, handles_ok, posts}

CLI (durable — routine / daemon 都可调):
  status
  mark-quota [--reason TEXT]     # 翻到 6551，跳过内置 X search
  mark-x-ok [--reason TEXT]      # 翻回 x
  maybe-restore                  # UTC 日切过 since → 建议/自动翻回 x
  fetch-6551 [--handles a,b] [--max N] [--n 5] [--dry-run] [--force]
  on-quota [--reason TEXT]       # mark-quota + fetch-6551（routine 撞额度时调）
  run                            # maybe-restore；mode=x → print USE_X；mode=6551 → fetch
  daemon-tick                    # workbench_soon_watch 钩子：仅 mode=6551 且间隔到才拉

不碰 T-20 WSS / sniper_6551。不写 token。不宣称固定 CA 买入。
6551 PTS：优先今日清单 handles，再 round-robin 其余；默认每轮最多 5 个、n=5。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
ALERT = BASE / "alerts"
PLAN = ALERT / "workbench_soon_x_plan.json"
STATE = ALERT / "x_quota_fallback.json"
INBOX = ALERT / "x_inbox"
ERR_LOG = ALERT / "workbench_soon_x_fetch_errors.log"
SH = ZoneInfo("Asia/Shanghai")

DEFAULT_MAX = int(os.environ.get("WB_X_6551_MAX", "5"))
DEFAULT_N = int(os.environ.get("WB_X_6551_N", "5"))
MIN_INTERVAL_S = int(os.environ.get("WB_X_6551_INTERVAL", "280"))  # ~5min, slightly under routine


def now_sh() -> datetime:
    return datetime.now(SH)


def iso(dt: datetime | None = None) -> str:
    return (dt or now_sh()).isoformat(timespec="seconds")


def utc_day(dt: datetime | None = None) -> str:
    d = dt or datetime.now(timezone.utc)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).strftime("%Y-%m-%d")


def next_reset_hint(from_dt: datetime | None = None) -> str:
    """Built-in X resets 00:00 UTC = 08:00 Asia/Shanghai."""
    now = from_dt or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)
    # next 00:00 UTC
    from datetime import timedelta
    nxt = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    if now.hour == 0 and now.minute == 0 and now.second == 0:
        nxt = now
    sh = nxt.astimezone(SH)
    return f"resets {nxt.strftime('%Y-%m-%dT00:00Z')} / {sh.strftime('%Y-%m-%d %H:%M')} Asia/Shanghai"


def load_state() -> dict:
    try:
        st = json.loads(STATE.read_text(encoding="utf-8"))
        if isinstance(st, dict):
            return st
    except Exception:
        pass
    return {"mode": "x", "since": None, "reason": None, "reset_hint": None}


def save_state(st: dict) -> None:
    ALERT.mkdir(parents=True, exist_ok=True)
    st = dict(st)
    st["updated_at"] = iso()
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(STATE)


def log_err(msg: str) -> None:
    ALERT.mkdir(parents=True, exist_ok=True)
    line = f"{iso()} {msg}\n"
    try:
        with ERR_LOG.open("a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def load_plan() -> dict:
    try:
        return json.loads(PLAN.read_text(encoding="utf-8"))
    except Exception:
        return {}


def today_boost() -> list[str]:
    try:
        # avoid circular import cost: read today list file if present
        sys.path.insert(0, str(BASE))
        from workbench_soon_watch import today_boost_handles  # type: ignore

        hs = sorted({str(h).lstrip("@") for h in (today_boost_handles() or set()) if h})
        return hs
    except Exception:
        return []


def plan_handles() -> list[str]:
    plan = load_plan()
    out = []
    seen = set()
    for h in plan.get("handles") or []:
        c = str(h or "").lstrip("@").strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


def casing_map() -> dict[str, str]:
    """lower -> preferred screen name (from prior 6551 successes, then plan)."""
    m = {}
    for h in plan_handles():
        m[h.lower()] = h
    st = load_state()
    for k, v in (st.get("casings") or {}).items():
        if v:
            m[str(k).lower()] = str(v).lstrip("@")
    return m


def remember_casing(handle: str, screen: str | None = None) -> None:
    screen = (screen or handle or "").lstrip("@").strip()
    if not screen:
        return
    st = load_state()
    cas = dict(st.get("casings") or {})
    cas[screen.lower()] = screen
    st["casings"] = cas
    save_state(st)


def pick_handles(explicit: list[str] | None, max_n: int, rr_offset: int) -> tuple[list[str], int]:
    """今日清单优先，其余 round-robin。返回 (handles, new_rr_offset)。

    Prefer casing from workbench_soon_x_plan.json (6551 username is case-sensitive).
    """
    all_h = plan_handles()
    by_lower = casing_map()
    for h in all_h:
        by_lower.setdefault(h.lower(), h)

    def canon(h: str) -> str:
        h = str(h or "").lstrip("@").strip()
        return by_lower.get(h.lower(), h)

    if explicit:
        # keep caller casing (plan often lowercases; 6551 is picky)
        return [str(h).lstrip("@").strip() for h in explicit[:max_n]], rr_offset
    boost = [canon(h) for h in today_boost()]
    # de-dupe boost preserving order
    seen = set()
    boost_u = []
    for h in boost:
        if h.lower() in seen:
            continue
        seen.add(h.lower())
        boost_u.append(h)
    boost = boost_u
    rest = [h for h in all_h if h.lower() not in seen]
    picked = list(boost[:max_n])
    if len(picked) < max_n and rest:
        start = rr_offset % len(rest)
        rotated = rest[start:] + rest[:start]
        for h in rotated:
            if len(picked) >= max_n:
                break
            picked.append(h)
        took_rest = max(0, len(picked) - len(boost))
        rr_offset = (start + took_rest) % len(rest)
    return picked, rr_offset


def to_iso_created(val) -> str:
    if not val:
        return ""
    s = str(val)
    try:
        if "T" in s or s.endswith("Z"):
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    except Exception:
        return s


def tweet_to_x_post(tw: dict, handle: str) -> dict | None:
    if not isinstance(tw, dict):
        return None
    pid = str(tw.get("id") or tw.get("id_str") or "")
    text = tw.get("text") or tw.get("full_text") or ""
    if not pid and not text:
        return None
    uname = (tw.get("userScreenName") or tw.get("username") or handle or "").lstrip("@")
    uid = str(tw.get("userIdStr") or tw.get("user_id") or tw.get("author_id") or "")
    created = to_iso_created(tw.get("createdAt") or tw.get("created_at") or "")
    url = tw.get("url") or (f"https://x.com/{uname}/status/{pid}" if pid and uname else "")
    post = {
        "author_id": uid,
        "created_at": created,
        "id": pid,
        "text": text,
        "url": url,
    }
    # keep light metrics if present (harmless for ingest)
    pm = {}
    if tw.get("favoriteCount") is not None:
        pm["like_count"] = tw.get("favoriteCount")
    if tw.get("replyCount") is not None:
        pm["reply_count"] = tw.get("replyCount")
    if tw.get("viewCount") is not None:
        pm["impression_count"] = tw.get("viewCount")
    if pm:
        post["public_metrics"] = pm
    return post


def build_inbox_doc(handle_tweets: dict[str, list[dict]]) -> dict:
    data = []
    users = {}
    for handle, tweets in handle_tweets.items():
        for tw in tweets:
            post = tweet_to_x_post(tw, handle)
            if not post:
                continue
            data.append(post)
            uid = post.get("author_id") or ""
            uname = (tw.get("userScreenName") or handle).lstrip("@")
            name = tw.get("userName") or uname
            key = uid or uname.lower()
            if key not in users:
                users[key] = {"id": uid or uname, "name": name, "username": uname}
    # stable-ish: newest first if created_at sortable
    data.sort(key=lambda p: p.get("created_at") or "", reverse=True)
    user_list = list(users.values())
    return {
        "data": data,
        "includes": {"users": user_list},
        "meta": {
            "result_count": len(data),
            "source": "6551",
            "fetched_via": "6551_user_tweets",
        },
        "source": "6551",
        "fetched_via": "6551_user_tweets",
        "handles": list(handle_tweets.keys()),
    }


def write_inbox(doc: dict, tag: str = "6551") -> Path:
    INBOX.mkdir(parents=True, exist_ok=True)
    (INBOX / "done").mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = INBOX / f"{ts}_{tag}.json"
    path.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def mark_quota(reason: str = "X daily read limit 1000") -> dict:
    st = load_state()
    st["mode"] = "6551"
    st["since"] = iso()
    st["reason"] = reason
    st["reset_hint"] = next_reset_hint()
    st["flipped_at"] = iso()
    save_state(st)
    log_err(f"fallback→6551 — {reason} ({st['reset_hint']})")
    return st


def mark_x_ok(reason: str = "quota restored / probe ok") -> dict:
    st = load_state()
    st["mode"] = "x"
    st["since"] = iso()
    st["reason"] = reason
    st["reset_hint"] = next_reset_hint()
    st["restored_at"] = iso()
    save_state(st)
    log_err(f"fallback→x — {reason}")
    return st


def maybe_restore(*, auto: bool = True) -> dict:
    """If mode=6551 and UTC day advanced past flip day, flip back to x."""
    st = load_state()
    out = {"mode": st.get("mode"), "restored": False, "reason": None}
    if st.get("mode") != "6551":
        return {**out, "state": st}
    since = st.get("since") or st.get("flipped_at")
    flip_day = None
    if since:
        try:
            dt = datetime.fromisoformat(str(since).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=SH)
            flip_day = utc_day(dt.astimezone(timezone.utc))
        except Exception:
            flip_day = None
    today = utc_day()
    out["flip_utc_day"] = flip_day
    out["today_utc_day"] = today
    if flip_day and today > flip_day:
        out["reason"] = f"UTC day rolled {flip_day}→{today}; try built-in X again"
        if auto:
            st = mark_x_ok(out["reason"])
            out["restored"] = True
            out["mode"] = "x"
        else:
            out["should_restore"] = True
    out["state"] = load_state()
    return out


def fetch_6551(
    *,
    handles: list[str] | None = None,
    max_n: int = DEFAULT_MAX,
    n_tweets: int = DEFAULT_N,
    dry_run: bool = False,
    force: bool = False,
) -> dict:
    st = load_state()
    if st.get("mode") != "6551" and not force and not handles:
        return {"ok": False, "skipped": True, "reason": "mode!=6551 (pass --force)", "mode": st.get("mode")}

    # interval guard (unless force / explicit handles for smoke)
    last = st.get("last_fetch_at")
    if last and not force and not handles:
        try:
            prev = datetime.fromisoformat(str(last))
            if prev.tzinfo is None:
                prev = prev.replace(tzinfo=SH)
            age = (now_sh() - prev.astimezone(SH)).total_seconds()
            if age < MIN_INTERVAL_S:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": f"interval {int(age)}s < {MIN_INTERVAL_S}s",
                    "mode": st.get("mode"),
                }
        except Exception:
            pass

    rr = int(st.get("rr_offset") or 0)
    picked, new_rr = pick_handles(handles, max_n, rr)
    if not picked:
        return {"ok": False, "error": "no handles", "mode": st.get("mode")}

    try:
        import x6551
        from x6551 import X6551Error
    except Exception as e:
        return {"ok": False, "error": f"import x6551 failed: {e}"}

    handle_tweets: dict[str, list[dict]] = {}
    errors = []
    ok_handles = []
    for h in picked:
        last_err = None
        tw = None
        for attempt in range(3):
            try:
                tw = x6551.user_tweets(h, n=n_tweets, replies=False)
                last_err = None
                break
            except Exception as e:
                last_err = e
                status = getattr(e, "status", None)
                msg = str(e)
                # transient 400 "try again later" — brief backoff
                if status == 400 and "try again" in msg.lower() and attempt < 2:
                    time.sleep(0.8 * (attempt + 1))
                    continue
                break
        if last_err is None and tw is not None:
            handle_tweets[h] = tw if isinstance(tw, list) else []
            ok_handles.append(h)
            screen = None
            if isinstance(tw, list) and tw:
                screen = (tw[0] or {}).get("userScreenName") or (tw[0] or {}).get("username")
            try:
                remember_casing(h, screen or h)
            except Exception:
                pass
            time.sleep(0.25)
            continue
        e = last_err
        status = getattr(e, "status", None) if e else None
        msg = str(e) if e else "unknown"
        errors.append({"handle": h, "status": status, "error": msg[:200]})
        if status in (402, 403):
            log_err(f"6551 {status} on user_tweets @{h} — {msg[:160]}")
            break
        log_err(f"6551 fetch @{h} failed — {msg[:160]}")
        time.sleep(0.25)

    posts = sum(len(v) for v in handle_tweets.values())
    result = {
        "ok": bool(ok_handles) or not errors,
        "mode": "6551",
        "handles": picked,
        "handles_ok": ok_handles,
        "posts": posts,
        "errors": errors,
        "dry_run": dry_run,
    }

    if dry_run:
        result["sample"] = {
            h: (handle_tweets[h][:1] if handle_tweets.get(h) else [])
            for h in ok_handles[:2]
        }
        return result

    if not handle_tweets:
        st = load_state()
        st["last_fetch_at"] = iso()
        st["last_fetch"] = result
        st["last_error"] = errors[:3] if errors else "no tweets"
        st["rr_offset"] = new_rr
        save_state(st)
        result["ok"] = False
        result["inbox"] = None
        return result

    doc = build_inbox_doc(handle_tweets)
    path = write_inbox(doc, tag="6551")
    result["inbox"] = str(path)
    result["result_count"] = doc["meta"]["result_count"]

    st = load_state()
    if force or st.get("mode") != "6551":
        # smoke / forced: don't flip mode unless already 6551; still record fetch
        pass
    st["mode"] = st.get("mode") or "6551"
    if force and st.get("mode") != "6551":
        # keep prior mode for smoke unless caller marked quota
        pass
    st["last_fetch_at"] = iso()
    st["last_fetch"] = {
        "at": iso(),
        "handles_ok": ok_handles,
        "posts": posts,
        "inbox": str(path),
        "errors": errors[:5],
    }
    st["rr_offset"] = new_rr
    if errors:
        st["last_error"] = errors[:3]
    else:
        st["last_error"] = None
    save_state(st)
    return result


def on_quota(reason: str = "search_posts_all blocked — X daily read limit 1000") -> dict:
    st = mark_quota(reason)
    fr = fetch_6551(force=True)
    return {"state": st, "fetch": fr}


def recent_quota_block_in_log(max_age_s: int = 900) -> str | None:
    """If routine only logged quota errors (old behavior), detect and flip."""
    try:
        raw = ERR_LOG.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
    lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
    if not lines:
        return None
    import re
    for ln in reversed(lines[-40:]):
        low = ln.lower()
        # Only real built-in X blocks — ignore our own fallback→x/6551 state lines.
        if "fallback→" in ln or "fallback->" in low:
            continue
        if "search_posts_all blocked" in low or "daily read limit" in low:
            pass
        elif "usage capped" in low or ("x " in low and "1000" in low and "limit" in low):
            pass
        else:
            continue
        # parse leading iso timestamp if present
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T[^\s]+)", ln)
        if m:
            try:
                dt = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=SH)
                age = (now_sh() - dt.astimezone(SH)).total_seconds()
                if age > max_age_s:
                    return None
            except Exception:
                pass
        return ln[:240]
    return None


def daemon_tick() -> dict:
    """Called from workbench_soon_watch x_cycle. Quiet no-op when mode=x (unless log shows quota)."""
    maybe_restore(auto=True)
    st = load_state()
    if st.get("mode") != "6551":
        hit = recent_quota_block_in_log()
        if hit:
            mark_quota(f"detected from error log: {hit[:160]}")
            return fetch_6551(force=True)
        return {"ok": True, "skipped": True, "mode": st.get("mode")}
    return fetch_6551(force=False)


def cmd_run() -> dict:
    mr = maybe_restore(auto=True)
    st = load_state()
    if st.get("mode") == "x":
        return {
            "action": "USE_X",
            "mode": "x",
            "restored": mr.get("restored"),
            "hint": "Call built-in X search_posts_all for plan queries; on quota → on-quota",
            "plan": str(PLAN),
            "inbox": str(INBOX),
            "state": st,
        }
    fr = fetch_6551(force=False)
    return {"action": "USE_6551", "mode": "6551", "fetch": fr, "state": load_state()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Workbench X↔6551 quota fallback")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status")
    p_mq = sub.add_parser("mark-quota")
    p_mq.add_argument("--reason", default="X daily read limit 1000")
    p_xo = sub.add_parser("mark-x-ok")
    p_xo.add_argument("--reason", default="quota restored / probe ok")
    p_mr = sub.add_parser("maybe-restore")
    p_mr.add_argument("--no-auto", action="store_true")
    p_f = sub.add_parser("fetch-6551")
    p_f.add_argument("--handles", default="", help="comma-separated; default=plan priority")
    p_f.add_argument("--max", type=int, default=DEFAULT_MAX)
    p_f.add_argument("--n", type=int, default=DEFAULT_N)
    p_f.add_argument("--dry-run", action="store_true")
    p_f.add_argument("--force", action="store_true")
    p_oq = sub.add_parser("on-quota")
    p_oq.add_argument("--reason", default="search_posts_all blocked — X daily read limit 1000")
    sub.add_parser("run")
    sub.add_parser("daemon-tick")

    args = ap.parse_args()
    if args.cmd == "status":
        st = load_state()
        print(json.dumps({"state": st, "plan_handles": len(plan_handles()), "today_boost": today_boost()}, ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "mark-quota":
        print(json.dumps(mark_quota(args.reason), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "mark-x-ok":
        print(json.dumps(mark_x_ok(args.reason), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "maybe-restore":
        print(json.dumps(maybe_restore(auto=not args.no_auto), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "fetch-6551":
        hs = [h.strip().lstrip("@") for h in args.handles.split(",") if h.strip()] or None
        print(json.dumps(fetch_6551(handles=hs, max_n=args.max, n_tweets=args.n, dry_run=args.dry_run, force=args.force), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "on-quota":
        print(json.dumps(on_quota(args.reason), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "run":
        print(json.dumps(cmd_run(), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "daemon-tick":
        print(json.dumps(daemon_tick(), ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
