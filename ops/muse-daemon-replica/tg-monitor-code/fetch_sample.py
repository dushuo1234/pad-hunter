import os, json, asyncio, re
from pathlib import Path
from urllib.parse import urlparse

BASE = Path("/home/box/.tg-monitor")
ENV = BASE / ".env"
SESSION = str(BASE / "tg.session")
TARGET_FILE = BASE / "target.json"
OUT = BASE / "sample_messages.json"

URL_RE = re.compile(r"https?://[^\s<>\"']+|t\.me/[^\s<>\"']+", re.I)
CHAIN_KW = [
    "sol", "solana", "eth", "ethereum", "bsc", "bnb", "base", "arbitrum", "arb",
    "polygon", "matic", "avax", "avalanche", "ton", "tron", "sui", "aptos",
    "blast", "optimism", "op", "fantom", "ftm", "sei", "injective", "near",
    "链", "公链", "链上",
]
LAUNCH_KW = [
    "pump.fun", "pumpfun", "pump", "raydium", "jupiter", "uniswap", "pancakeswap",
    "gmgn", "dexscreener", "birdeye", "moonshot", "letsbonk", "bonk", "发射台",
    "launchpad", "launch", "presale", "fair launch", "bonding",
]
CA_HINT = re.compile(r"\b(0x[a-fA-F0-9]{40}|[1-9A-HJ-NP-Za-km-z]{32,44})\b")

def load_env():
    cfg = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg

def find_urls(text):
    if not text:
        return []
    return list(dict.fromkeys(URL_RE.findall(text)))

def detect_keywords(text):
    if not text:
        return [], []
    low = text.lower()
    chains = [k for k in CHAIN_KW if k.lower() in low or k in text]
    launches = [k for k in LAUNCH_KW if k.lower() in low or k in text]
    # dedupe preserving order
    def uniq(xs):
        seen = set()
        out = []
        for x in xs:
            xl = x.lower()
            if xl not in seen:
                seen.add(xl)
                out.append(x)
        return out
    return uniq(chains), uniq(launches)

def redact_preview(text, n=80):
    if not text:
        return ""
    t = text.replace("\n", " ").strip()
    # redact invite-looking links / private tokens
    t = re.sub(r"t\.me/\+[A-Za-z0-9_-]+", "t.me/+REDACTED", t, flags=re.I)
    t = re.sub(r"t\.me/joinchat/[A-Za-z0-9_-]+", "t.me/joinchat/REDACTED", t, flags=re.I)
    t = re.sub(r"https?://t\.me/\+[A-Za-z0-9_-]+", "https://t.me/+REDACTED", t, flags=re.I)
    if len(t) > n:
        t = t[:n] + "…"
    return t

def infer_pattern(texts):
    labels = []
    joined = "\n".join(t for t in texts if t)
    for label in ["链", "发射台", "合约", "CA", "合约地址", "代币", "项目名", "官网", "推特", "Twitter", "TG", "电报", "社区", "开盘", "上线"]:
        if label.lower() in joined.lower() or label in joined:
            labels.append(label)
    # line-prefix style: "xxx：" or "xxx:"
    prefixes = re.findall(r"(?m)^[\s\*•\-]*([^\n:：]{1,12})[:：]", joined)
    common_pref = []
    from collections import Counter
    for p, c in Counter(prefixes).most_common(12):
        if c >= 2 and p.strip():
            common_pref.append(f"{p.strip()}(x{c})")
    return {"field_labels_seen": labels, "repeated_line_prefixes": common_pref}

async def main():
    result = {
        "fetch_ok": False,
        "count": 0,
        "error_type": None,
        "error_message": None,
        "summaries": [],
        "pattern": None,
        "proxy_used": False,
        "authorized": False,
    }
    try:
        cfg = load_env()
        api_id = int(cfg["TG_API_ID"])
        api_hash = cfg["TG_API_HASH"]
        proxy = None
        if cfg.get("TG_PROXY_HOST") and cfg.get("TG_PROXY_PORT"):
            ptype = cfg.get("TG_PROXY_TYPE", "http").lower()
            proxy = (ptype, cfg["TG_PROXY_HOST"], int(cfg["TG_PROXY_PORT"]), True,
                     cfg.get("TG_PROXY_USER") or None, cfg.get("TG_PROXY_PASS") or None)
            result["proxy_used"] = True
            print(f"proxy used: yes ({ptype})")
        else:
            print("proxy used: no")

        target = json.loads(TARGET_FILE.read_text())
        peer = target.get("peer_id") or target.get("id")
        print(f"target peer: {peer} title={target.get('title')}")

        from telethon import TelegramClient

        kwargs = dict(
            proxy=proxy,
            connection_retries=30,
            retry_delay=2,
            timeout=30,
        ) if proxy else dict(connection_retries=30, retry_delay=2, timeout=30)
        client = TelegramClient(SESSION, api_id, api_hash, **kwargs)
        try:
            await client.connect()
            print("telegram connect ok")
            authorized = await client.is_user_authorized()
            result["authorized"] = bool(authorized)
            print(f"authorized: {authorized}")
            if not authorized:
                result["error_type"] = "NotAuthorized"
                result["error_message"] = "session not authorized"
                print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))
                return

            entity = await client.get_entity(peer)
            msgs = []
            async for m in client.iter_messages(entity, limit=10):
                text = m.message or m.text or ""
                urls = find_urls(text)
                sender_id = None
                try:
                    sender_id = m.sender_id
                except Exception:
                    sender_id = None
                date_iso = m.date.isoformat() if m.date else None
                msgs.append({
                    "id": m.id,
                    "date": date_iso,
                    "sender_id": sender_id,
                    "text": text,
                    "has_media": bool(m.media),
                    "urls": urls,
                })

            OUT.write_text(json.dumps(msgs, ensure_ascii=False, indent=2))
            os.chmod(OUT, 0o600)
            result["fetch_ok"] = True
            result["count"] = len(msgs)
            print(f"fetched: {len(msgs)} saved to sample_messages.json")

            texts = [m["text"] for m in msgs]
            result["pattern"] = infer_pattern(texts)

            for m in msgs[:5]:
                chains, launches = detect_keywords(m["text"])
                has_links = bool(m["urls"])
                has_ca = bool(CA_HINT.search(m["text"] or ""))
                result["summaries"].append({
                    "id": m["id"],
                    "date": m["date"],
                    "approx_len": len(m["text"] or ""),
                    "has_links": has_links,
                    "has_ca_like": has_ca,
                    "has_media": m["has_media"],
                    "chain_keywords": chains,
                    "launchpad_keywords": launches,
                    "preview": redact_preview(m["text"], 80),
                })
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    except Exception as e:
        result["error_type"] = type(e).__name__
        # scrub possible secrets from error strings
        msg = str(e)[:300]
        msg = re.sub(r"(password|hash|api[_-]?hash|proxy.?pass)[=:].*", r"\1=REDACTED", msg, flags=re.I)
        result["error_message"] = msg
        print(f"error: {result['error_type']}: {result['error_message']}")

    print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
