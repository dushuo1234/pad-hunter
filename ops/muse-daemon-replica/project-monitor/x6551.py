#!/usr/bin/env python3
"""Minimal 6551 (NewsLiquid OpenTwitter) REST client.

Sniper WSS last-layer entry: sniper_6551.py (watch/inject/smoke).
Token: secrets/6551_token or env OPENNEWS_TOKEN (never logged). Base: https://ai.6551.io, POST JSON, Bearer auth.
Billing: user_tweets/search = 1 PTS per 20 results; user_info/tweet_by_id = 1 PTS/call.
Free plan = 5 PTS/day. Watch list + WSS (wss://ai.6551.io/open/twitter_wss) need Max plan.
Errors: 401 invalid token, 402 insufficient quota, 403 needs paid plan.
Usage: python3 x6551.py probe | tweets <handle> [n] | search <keywords> [n]
"""
from __future__ import annotations
import json, sys, time, urllib.request, urllib.error
from pathlib import Path

BASE_URL = "https://ai.6551.io/open/"
TOKEN_FILE = Path(__file__).resolve().parent / "secrets" / "6551_token"


def _token() -> str:
    import os
    for k in ("SNIPER_6551_TOKEN", "OPENNEWS_TOKEN", "OPENTWITTER_API_KEY", "X6551_TOKEN"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return TOKEN_FILE.read_text().strip()


class X6551Error(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__(f"{status}: {msg}"); self.status = status


def _post(ep: str, body: dict, timeout: float = 15.0) -> dict:
    req = urllib.request.Request(BASE_URL + ep, data=json.dumps(body).encode(), method="POST",
                                 headers={"Authorization": "Bearer " + _token(),
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try: msg = json.loads(e.read()).get("error", "")
        except Exception: msg = ""
        raise X6551Error(e.code, msg) from None


def user_tweets(handle: str, n: int = 20, replies: bool = False) -> list[dict]:
    d = _post("twitter_user_tweets", {"username": handle.lstrip("@"), "maxResults": n,
                                       "product": "Latest", "includeReplies": replies, "includeRetweets": False})
    return d.get("data") or []


def search(keywords: str, n: int = 20) -> list[dict]:
    return _post("twitter_search", {"keywords": keywords, "maxResults": n, "product": "Latest"}).get("data") or []


def probe() -> dict:
    """1 PTS if it works. Returns {'ok', 'status', 'error', 'latency_s'}."""
    t = time.time()
    try:
        _post("twitter_user_info", {"username": "TapeRobot_bsc"}); return {"ok": True, "latency_s": round(time.time()-t, 3)}
    except X6551Error as e:
        return {"ok": False, "status": e.status, "error": str(e), "latency_s": round(time.time()-t, 3)}


if __name__ == "__main__":
    a = sys.argv[1:] or ["probe"]
    if a[0] == "probe": print(json.dumps(probe()))
    elif a[0] == "tweets": print(json.dumps(user_tweets(a[1], int(a[2]) if len(a) > 2 else 5), ensure_ascii=False, indent=1))
    elif a[0] == "search": print(json.dumps(search(a[1], int(a[2]) if len(a) > 2 else 5), ensure_ascii=False, indent=1))
