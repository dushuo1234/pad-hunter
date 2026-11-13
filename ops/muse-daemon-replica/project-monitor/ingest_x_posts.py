#!/usr/bin/env python3
"""Merge X MCP get_users_posts / get_users_by_username JSON dumps into x_posts_cache.json.

Usage:
  python3 ingest_x_posts.py /tmp/x_posts_raw/*.json
  python3 ingest_x_posts.py --listing /tmp/x_listing_raw/*.json   # → x_listing_posts_cache.json

Accepts either a raw MCP tool result object, or {data:[posts], includes:{users:[…]}}.
Never invents tokens. Idempotent merge by post id.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
X_CACHE = BASE / "x_posts_cache.json"
X_LISTING = BASE / "x_listing_posts_cache.json"
SH = ZoneInfo("Asia/Shanghai")


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def normalize_post(p: dict, username: str | None = None) -> dict | None:
    if not isinstance(p, dict):
        return None
    # unwrap nested
    if "data" in p and isinstance(p["data"], dict) and "text" in p["data"]:
        p = p["data"]
    text = p.get("text") or p.get("full_text") or ""
    pid = str(p.get("id") or p.get("id_str") or "")
    if not text and not pid:
        return None
    uname = username or p.get("username") or p.get("author_username") or ""
    url = p.get("url") or ""
    if not url and pid and uname:
        url = f"https://x.com/{uname}/status/{pid}"
    return {
        "id": pid,
        "text": text,
        "created_at": p.get("created_at") or p.get("createdAt") or "",
        "url": url,
        "username": uname.lstrip("@"),
    }


def extract_posts_from_payload(doc: dict | list) -> list[tuple[str, dict]]:
    """Return list of (username, post)."""
    out: list[tuple[str, dict]] = []
    if isinstance(doc, list):
        for item in doc:
            out.extend(extract_posts_from_payload(item))
        return out
    if not isinstance(doc, dict):
        return out

    # MCP sometimes wraps as {result:…} or {content:…}
    for k in ("result", "data", "posts", "tweets"):
        if k in doc and doc[k] is not doc:
            # data may be list of posts
            if k == "data" and isinstance(doc["data"], list):
                users_by_id = {}
                includes = doc.get("includes") or {}
                for u in includes.get("users") or []:
                    if u.get("id"):
                        users_by_id[str(u["id"])] = u.get("username") or ""
                for p in doc["data"]:
                    author = ""
                    aid = str(p.get("author_id") or "")
                    if aid and aid in users_by_id:
                        author = users_by_id[aid]
                    author = author or p.get("username") or ""
                    np = normalize_post(p, author)
                    if np and np["username"]:
                        out.append((np["username"], np))
                return out
            out.extend(extract_posts_from_payload(doc[k]))

    # {users: {handle: {posts:[…]}}}
    if "users" in doc and isinstance(doc["users"], dict):
        for handle, u in doc["users"].items():
            if not isinstance(u, dict):
                continue
            for p in u.get("posts") or []:
                np = normalize_post(p, handle)
                if np:
                    out.append((handle.lstrip("@"), np))
        return out

    # single post
    if "text" in doc or "full_text" in doc:
        np = normalize_post(doc)
        if np and np["username"]:
            out.append((np["username"], np))
    return out


def merge_posts_cache(files: list[Path], listing: bool = False) -> int:
    path = X_LISTING if listing else X_CACHE
    cache = load(path) or {}
    if listing:
        users = cache.get("users") or {}
        # listing format: users[handle] = [posts]
        added = 0
        for f in files:
            try:
                doc = json.loads(f.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"WARN skip {f}: {e}")
                continue
            for handle, post in extract_posts_from_payload(doc):
                h = handle.lower()
                arr = users.get(h)
                if not isinstance(arr, list):
                    # migrate dict form
                    if isinstance(arr, dict):
                        arr = list(arr.get("posts") or [])
                    else:
                        arr = []
                ids = {p.get("id") for p in arr if isinstance(p, dict)}
                if post.get("id") and post["id"] in ids:
                    continue
                arr.insert(0, post)
                users[h] = arr[:50]
                added += 1
        cache["users"] = users
        cache["fetched_at"] = now_iso()
        cache["note"] = cache.get("note") or (
            "X recent posts (from:handles + launch keywords / per-user posts); used by extract_listing_times + scan_x_progress"
        )
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[{now_iso()}] listing cache +{added} posts → {path} users={len(users)}")
        return added

    users = cache.get("users") or {}
    added = 0
    for f in files:
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"WARN skip {f}: {e}")
            continue
        # also absorb user profile if present
        if isinstance(doc, dict):
            data = doc.get("data") if isinstance(doc.get("data"), dict) else None
            if data and data.get("username") and data.get("id"):
                uname = data["username"]
                entry = users.get(uname) or users.get(uname.lower()) or {}
                if not isinstance(entry, dict):
                    entry = {}
                entry.update({
                    "id": str(data.get("id")),
                    "username": uname,
                    "name": data.get("name") or entry.get("name"),
                    "description": data.get("description") or entry.get("description"),
                    "public_metrics": data.get("public_metrics") or entry.get("public_metrics"),
                    "url": data.get("url") or entry.get("url"),
                    "created_at": data.get("created_at") or entry.get("created_at"),
                })
                entry.setdefault("posts", [])
                users[uname] = entry

        for handle, post in extract_posts_from_payload(doc):
            # find user entry (case-insensitive key)
            key = None
            for k in list(users.keys()):
                if k.lower() == handle.lower():
                    key = k
                    break
            if key is None:
                key = handle
                users[key] = {"username": handle, "posts": [], "id": None}
            entry = users[key]
            if not isinstance(entry, dict):
                entry = {"username": handle, "posts": []}
                users[key] = entry
            posts = entry.get("posts") or []
            ids = {p.get("id") for p in posts if isinstance(p, dict)}
            if post.get("id") and post["id"] in ids:
                # refresh text
                for p in posts:
                    if p.get("id") == post["id"]:
                        p.update(post)
                        break
                continue
            posts.insert(0, post)
            entry["posts"] = posts[:40]
            entry["fetched_at"] = now_iso()
            if not entry.get("username"):
                entry["username"] = handle
            users[key] = entry
            added += 1

    cache["users"] = users
    cache["fetched_at"] = now_iso()
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[{now_iso()}] posts cache +{added} posts → {path} users={len(users)}")
    return added


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", type=Path)
    ap.add_argument("--listing", action="store_true")
    args = ap.parse_args()
    files = [f for f in args.files if f.exists()]
    if not files:
        print("no files")
        return 1
    merge_posts_cache(files, listing=args.listing)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
