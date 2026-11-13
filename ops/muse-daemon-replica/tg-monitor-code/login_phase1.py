import os, json, asyncio
from pathlib import Path

BASE = Path("/home/box/.tg-monitor")
ENV = BASE / ".env"
STATE = BASE / "login_state.json"
SESSION = str(BASE / "tg.session")

def load_env():
    cfg = {}
    for line in ENV.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k,v=line.split("=",1)
        cfg[k.strip()]=v.strip()
    return cfg

async def main():
    cfg = load_env()
    api_id = int(cfg["TG_API_ID"])
    api_hash = cfg["TG_API_HASH"]
    phone = cfg["TG_PHONE"]
    proxy = None
    if cfg.get("TG_PROXY_HOST") and cfg.get("TG_PROXY_PORT"):
        ptype = cfg.get("TG_PROXY_TYPE", "socks5").lower()
        proxy = (ptype, cfg["TG_PROXY_HOST"], int(cfg["TG_PROXY_PORT"]), True,
                 cfg.get("TG_PROXY_USER") or None, cfg.get("TG_PROXY_PASS") or None)
        print(f"proxy used: yes ({ptype})")
    else:
        print("proxy used: no")
    from telethon import TelegramClient
    kwargs = dict(proxy=proxy, connection_retries=20, retry_delay=2, timeout=20) if proxy else dict(connection_retries=20, retry_delay=2, timeout=20)
    client = TelegramClient(SESSION, api_id, api_hash, **kwargs)
    try:
        await client.connect()
        print("telegram connect ok")
        if await client.is_user_authorized():
            print("already authorized")
            return
        sent = await client.send_code_request(phone)
        state = {"phone": phone, "phone_code_hash": sent.phone_code_hash}
        STATE.write_text(json.dumps(state))
        os.chmod(STATE, 0o600)
        print("code sent")
        print(f"state file: {STATE}")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
