#!/usr/bin/env python3
"""Tiny TCP forwarder 127.0.0.1:8787 -> 127.0.0.1:8780 (workbench API).
Exists only because the Cloudflare dashboard route for api.adualpha.win points at :8787.
Raw TCP, so HTTP keep-alive and WebSocket upgrades pass through untouched.
Remove once the dashboard route is changed to http://127.0.0.1:8780."""
import asyncio, os
LISTEN = int(os.environ.get("CF_FWD_LISTEN", "8787"))
TARGET = int(os.environ.get("CF_FWD_TARGET", "8780"))

async def pipe(r, w):
    try:
        while True:
            data = await r.read(65536)
            if not data:
                break
            w.write(data)
            await w.drain()
    except Exception:
        pass
    finally:
        try:
            w.close()
        except Exception:
            pass

async def handle(cr, cw):
    try:
        ur, uw = await asyncio.open_connection("127.0.0.1", TARGET)
    except Exception:
        cw.close(); return
    await asyncio.gather(pipe(cr, uw), pipe(ur, cw))

async def main():
    srv = await asyncio.start_server(handle, "127.0.0.1", LISTEN, reuse_address=True)
    async with srv:
        await srv.serve_forever()

asyncio.run(main())
