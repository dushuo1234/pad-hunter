import os, json, asyncio
from pathlib import Path

BASE = Path("/home/box/.tg-monitor")
ENV = BASE / ".env"
SESSION = str(BASE / "tg.session")
TARGET_FILE = BASE / "target.json"

def load_env():
    cfg = {}
    for line in ENV.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg

async def main():
    result = {
        "signed_in": False,
        "twofa_needed": False,
        "group_found": False,
        "group_title": None,
        "group_id": None,
        "user_username": None,
        "user_first_name": None,
        "error_type": None,
        "error_message": None,
    }
    password = os.environ.get("TG_2FA_PASSWORD")
    if not password:
        result["error_type"] = "MissingEnv"
        result["error_message"] = "TG_2FA_PASSWORD not set in environment"
        print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))
        return
    try:
        cfg = load_env()
        api_id = int(cfg["TG_API_ID"])
        api_hash = cfg["TG_API_HASH"]
        proxy = None
        if cfg.get("TG_PROXY_HOST") and cfg.get("TG_PROXY_PORT"):
            ptype = cfg.get("TG_PROXY_TYPE", "http").lower()
            proxy = (ptype, cfg["TG_PROXY_HOST"], int(cfg["TG_PROXY_PORT"]), True,
                     cfg.get("TG_PROXY_USER") or None, cfg.get("TG_PROXY_PASS") or None)
            print(f"proxy used: yes ({ptype})")
        else:
            print("proxy used: no")

        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError

        kwargs = dict(proxy=proxy, connection_retries=30, retry_delay=2, timeout=30) if proxy else dict(connection_retries=30, retry_delay=2, timeout=30)
        client = TelegramClient(SESSION, api_id, api_hash, **kwargs)
        try:
            await client.connect()
            print("telegram connect ok")
            if not await client.is_user_authorized():
                try:
                    await client.sign_in(password=password)
                    print("2fa sign_in attempted")
                except SessionPasswordNeededError:
                    result["twofa_needed"] = True
                    result["error_type"] = "SessionPasswordNeededError"
                    result["error_message"] = "2FA password required or rejected as needed"
                    print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))
                    return
            else:
                print("already authorized before 2fa")

            authorized = await client.is_user_authorized()
            result["signed_in"] = bool(authorized)
            print(f"authorized: {authorized}")

            if authorized:
                me = await client.get_me()
                if me:
                    result["user_username"] = getattr(me, "username", None)
                    result["user_first_name"] = getattr(me, "first_name", None)
                    print(f"me username: {result['user_username'] or '(none)'}")
                    print(f"me first_name: {result['user_first_name'] or '(none)'}")

                target = "项目推送"
                found = None
                async for dialog in client.iter_dialogs():
                    title = dialog.name or ""
                    if title == target or target in title:
                        found = dialog
                        break
                if found:
                    entity_id = None
                    try:
                        entity_id = getattr(found.entity, "id", None)
                    except Exception:
                        entity_id = None
                    result["group_found"] = True
                    result["group_title"] = found.name
                    result["group_id"] = found.id
                    payload = {"title": found.name, "id": found.id, "entity_id": entity_id, "peer_id": found.id}
                    TARGET_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
                    os.chmod(TARGET_FILE, 0o600)
                    print(f"group found: {found.name} id={found.id}")
                else:
                    print("group not found among dialogs")
        finally:
            try:
                await client.disconnect()
            except Exception:
                pass
    except Exception as e:
        result["error_type"] = type(e).__name__
        result["error_message"] = str(e)[:300]
        print(f"error: {result['error_type']}: {result['error_message']}")
    finally:
        # ensure password reference not persisted; clear local var
        password = None
    print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
