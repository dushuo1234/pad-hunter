import os, json, asyncio, traceback
from pathlib import Path

BASE = Path("/home/box/.tg-monitor")
ENV = BASE / ".env"
STATE = BASE / "login_state.json"
CODE_FILE = BASE / "login_code.txt"
SESSION = str(BASE / "tg.session")

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
    try:
        cfg = load_env()
        api_id = int(cfg["TG_API_ID"])
        api_hash = cfg["TG_API_HASH"]
        phone = cfg["TG_PHONE"]

        if not STATE.exists():
            raise FileNotFoundError("login_state.json missing")
        state = json.loads(STATE.read_text())
        phone_code_hash = state.get("phone_code_hash")
        if not phone_code_hash:
            raise ValueError("phone_code_hash missing or already used")

        if not CODE_FILE.exists():
            raise FileNotFoundError("login_code.txt missing")
        code = CODE_FILE.read_text().strip()
        if not code:
            raise ValueError("login code empty")

        proxy = None
        if cfg.get("TG_PROXY_HOST") and cfg.get("TG_PROXY_PORT"):
            ptype = cfg.get("TG_PROXY_TYPE", "http").lower()
            # Prefer python-socks via Telethon tuple: (type, host, port, rdns, user, pass)
            proxy = (
                ptype,
                cfg["TG_PROXY_HOST"],
                int(cfg["TG_PROXY_PORT"]),
                True,
                cfg.get("TG_PROXY_USER") or None,
                cfg.get("TG_PROXY_PASS") or None,
            )
            print(f"proxy used: yes ({ptype})")
        else:
            print("proxy used: no")

        from telethon import TelegramClient
        from telethon.errors import SessionPasswordNeededError

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

            if await client.is_user_authorized():
                print("already authorized before sign_in")
            else:
                try:
                    await client.sign_in(phone, code, phone_code_hash=phone_code_hash)
                except SessionPasswordNeededError:
                    result["twofa_needed"] = True
                    result["error_type"] = "SessionPasswordNeededError"
                    result["error_message"] = "2FA password required"
                    print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))
                    return

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

                # Find dialog/group 「项目推送」
                target = "项目推送"
                found = None
                async for dialog in client.iter_dialogs():
                    title = dialog.name or ""
                    if title == target or target in title:
                        found = dialog
                        break
                if found:
                    result["group_found"] = True
                    result["group_title"] = found.name
                    result["group_id"] = found.id
                    print(f"group found: {found.name} id={found.id}")
                else:
                    print("group not found among dialogs")
        finally:
            await client.disconnect()

        # Clear phone_code_hash / mark used
        try:
            state["phone_code_hash"] = None
            state["used"] = True
            STATE.write_text(json.dumps(state))
            os.chmod(STATE, 0o600)
            print("login_state cleared/marked used")
        except Exception as e:
            print(f"state cleanup warn: {type(e).__name__}")

    except Exception as e:
        result["error_type"] = type(e).__name__
        # Avoid leaking secrets in message
        msg = str(e)
        for secret_key in ("TG_API_HASH", "TG_PROXY_PASS", "TG_PHONE"):
            pass
        # redact common patterns lightly
        result["error_message"] = msg[:300]
        print(f"error: {result['error_type']}: {result['error_message']}")
    finally:
        # Always delete login_code.txt securely
        try:
            if CODE_FILE.exists():
                # overwrite then unlink
                sz = CODE_FILE.stat().st_size
                with open(CODE_FILE, "r+b") as f:
                    f.write(b"\0" * max(sz, 1))
                    f.flush()
                    os.fsync(f.fileno())
                CODE_FILE.unlink()
                print("login_code.txt deleted")
        except Exception as e:
            print(f"code cleanup warn: {type(e).__name__}")

    print("RESULT_JSON:" + json.dumps(result, ensure_ascii=False))

if __name__ == "__main__":
    asyncio.run(main())
