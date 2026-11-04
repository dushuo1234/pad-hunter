#!/usr/bin/env python3
"""Manage Helius Solana webhooks for Pad Hunter launch monitoring.

Usage:
  solana_helius_setup.py ensure [--force-mass]  # workbench_only by default
  solana_helius_setup.py list     # list webhooks (redacts secrets in URLs)
  solana_helius_setup.py delete   # delete webhook tracked in state file

Never prints the API key or webhook secret.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path("/workspace/project-monitor")
KEY_FILE = BASE / ".helius_api_key"
SECRET_FILE = BASE / ".helius_webhook_secret"
STATE_FILE = BASE / "helius_webhook_state.json"
FACTORIES = BASE / "solana_factories.json"
PUBLIC_URL = BASE / "workbench_api_public_url.txt"
SH = ZoneInfo("Asia/Shanghai")
API_BASE = "https://mainnet.helius-rpc.com/v0/webhooks"

PREF_FILE = BASE / "solana_scan_pref.json"
WORKBENCH = BASE / "workbench_active.json"


def load_pref() -> dict:
    try:
        return json.loads(PREF_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"mode": "workbench_only"}


def workbench_solana_handles() -> list[str]:
    try:
        wb = json.loads(WORKBENCH.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for it in wb.get("items") or []:
        chain = f"{it.get('chain') or ''} {it.get('ca_chain') or ''}".lower()
        if "sol" in chain:
            h = (it.get("handle") or "").lstrip("@")
            if h:
                out.append(h)
    return out



# Prefer launchpads; skip high-volume Raydium AMM pools (every swap would burn credits).
PRIMARY_PROGRAM_IDS = [
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P",  # Pump.fun bonding
    "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA",  # PumpSwap
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj",  # Raydium LaunchLab
    "MoonCVVNZFSYkqNXP6bxHLPL6QQJiMagDL3qcqUQTrG",  # Moonshot
]


def now_iso() -> str:
    return datetime.now(SH).isoformat(timespec="seconds")


def api_key() -> str:
    k = (os.environ.get("HELIUS_API_KEY") or "").strip()
    if not k and KEY_FILE.exists():
        k = KEY_FILE.read_text().strip()
    if not k:
        raise SystemExit("HELIUS_API_KEY missing (env or .helius_api_key)")
    return k


def webhook_secret() -> str:
    if not SECRET_FILE.exists() or not SECRET_FILE.read_text().strip():
        import secrets

        SECRET_FILE.write_text(secrets.token_urlsafe(32) + "\n")
        os.chmod(SECRET_FILE, 0o600)
    return SECRET_FILE.read_text().strip()


def public_base() -> str:
    if PUBLIC_URL.exists():
        u = PUBLIC_URL.read_text().strip().rstrip("/")
        if u.startswith("https://"):
            return u
    return "https://dotted-disengage-awoke.ngrok-free.dev"


def webhook_url(secret: str) -> str:
    return f"{public_base()}/hooks/helius/solana?secret={secret}"


def redact_url(url: str) -> str:
    if not url:
        return url
    if "secret=" in url:
        pre, _, rest = url.partition("secret=")
        # keep only first few chars of secret for debugging identity
        sec = rest.split("&", 1)[0]
        tail = rest[len(sec) :] if len(rest) > len(sec) else ""
        return f"{pre}secret=***{tail}"
    return url


def http_json(method: str, url: str, body: dict | None = None) -> tuple[int, object]:
    data = None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = resp.getcode()
            if not raw or raw.strip() in ("", "null"):
                return code, None
            return code, json.loads(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {"error": str(e)}
        except Exception:
            parsed = {"error": raw[:500] or str(e)}
        return e.code, parsed
    except Exception as e:
        return 0, {"error": str(e)[:300]}


def authed(path: str = "") -> str:
    # Never log this URL (contains api key)
    return f"{API_BASE}{path}?api-key={api_key()}"


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_state(doc: dict) -> None:
    # Ensure no api key leaked into state
    blob = json.dumps(doc, ensure_ascii=False)
    if api_key() in blob:
        raise SystemExit("refusing to write state that contains api key")
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o644)
    tmp.replace(STATE_FILE)


def program_ids() -> list[str]:
    # Start from PRIMARY; merge any launchpad ids from factories file
    ids = list(PRIMARY_PROGRAM_IDS)
    fac = {}
    try:
        fac = json.loads(FACTORIES.read_text(encoding="utf-8"))
    except Exception:
        pass
    for p in fac.get("programs") or []:
        kind = (p.get("kind") or "").lower()
        pid = p.get("program_id")
        if not pid:
            continue
        if kind == "launchpad" or pid in PRIMARY_PROGRAM_IDS:
            if pid not in ids:
                ids.append(pid)
    return ids


def cmd_list() -> int:
    code, data = http_json("GET", authed(""))
    if code != 200:
        print(f"list_failed http={code} err={data}")
        return 1
    rows = data if isinstance(data, list) else []
    print(f"webhooks={len(rows)}")
    for w in rows:
        if not isinstance(w, dict):
            continue
        print(
            json.dumps(
                {
                    "webhookID": w.get("webhookID") or w.get("webhookId"),
                    "webhookType": w.get("webhookType"),
                    "webhookURL": redact_url(w.get("webhookURL") or ""),
                    "accountAddresses": w.get("accountAddresses"),
                    "transactionTypes": w.get("transactionTypes"),
                    "active": w.get("active", True),
                },
                ensure_ascii=False,
            )
        )
    return 0


def cmd_delete() -> int:
    st = load_state()
    wid = st.get("webhook_id")
    if not wid:
        print("no webhook_id in helius_webhook_state.json")
        return 1
    code, data = http_json("DELETE", authed(f"/{wid}"))
    print(f"delete http={code} webhook_id={wid}")
    ok = code in (200, 204) or (
        isinstance(data, dict) and "deleted" in str(data.get("message") or "").lower()
    )
    if ok:
        st["deleted_at"] = now_iso()
        st["webhook_id"] = None
        st["status"] = "deleted"
        save_state(st)
        try:
            fac = json.loads(FACTORIES.read_text(encoding="utf-8"))
            fac["status"] = "helius_webhook_disabled_workbench_only"
            fac["helius_webhook_id"] = None
            fac["updated_at"] = now_iso()
            FACTORIES.write_text(json.dumps(fac, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except Exception:
            pass
        return 0
    print(f"delete_failed {data}")
    return 1


def cmd_ensure(*, force_mass: bool = False) -> int:
    """Create/update Helius webhook.

    Default (solana_scan_pref mode=workbench_only): refuse mass pump/raydium watch.
    Only create when workbench has Solana items, or --force-mass is set.
    If workbench_only and no Solana on workbench: delete any existing webhook.
    """
    pref = load_pref()
    mode = (pref.get("mode") or "workbench_only").strip().lower()
    wb_sol = workbench_solana_handles()
    if mode == "workbench_only" and not force_mass:
        if not wb_sol:
            st = load_state()
            if st.get("webhook_id"):
                print("workbench_only: no Solana on workbench -> deleting mass Helius webhook")
                return cmd_delete()
            print("workbench_only: no Solana on workbench; webhook not created (receiver stays)")
            return 0
        print(f"workbench_only: Solana on workbench={wb_sol}; ensuring scoped launchpad webhook")
    elif force_mass:
        print("WARNING: --force-mass creating always-on launchpad webhook (costs credits)")
    secret = webhook_secret()
    url = webhook_url(secret)
    accounts = program_ids()
    body = {
        "webhookURL": url,
        "webhookType": "enhanced",
        # Empty / ANY = all types involving these program accounts (Pump create included)
        "transactionTypes": ["ANY"],
        "accountAddresses": accounts,
        "authHeader": f"Bearer {secret}",
        "txnStatus": "success",
    }
    st = load_state()
    wid = st.get("webhook_id")
    if wid:
        code, data = http_json("PUT", authed(f"/{wid}"), body)
        if code == 200 and isinstance(data, dict):
            new_id = data.get("webhookID") or data.get("webhookId") or wid
            _write_ok_state(new_id, accounts, data)
            print(f"updated webhook_id={new_id} programs={len(accounts)}")
            return 0
        print(f"update_failed http={code}; will create new. detail_keys={list(data) if isinstance(data, dict) else type(data)}")
        # fall through to create

    code, data = http_json("POST", authed(""), body)
    if code in (200, 201) and isinstance(data, dict):
        new_id = data.get("webhookID") or data.get("webhookId")
        if not new_id:
            print(f"create_ok_but_no_id keys={list(data.keys())}")
            return 1
        _write_ok_state(new_id, accounts, data)
        print(f"created webhook_id={new_id} programs={len(accounts)}")
        return 0

    # Plan / limit errors — report without secrets
    err = data if isinstance(data, dict) else {"error": str(data)}
    msg = json.dumps(err, ensure_ascii=False)[:500]
    # scrub accidental secret/key
    msg = msg.replace(secret, "***")
    try:
        msg = msg.replace(api_key(), "***")
    except Exception:
        pass
    print(f"create_failed http={code} {msg}")
    return 1


def _write_ok_state(webhook_id: str, accounts: list[str], raw: dict) -> None:
    doc = {
        "updated_at": now_iso(),
        "timezone": "Asia/Shanghai",
        "webhook_id": webhook_id,
        "webhook_type": raw.get("webhookType") or "enhanced",
        "webhook_url_base": f"{public_base()}/hooks/helius/solana",
        "auth": "query_secret_and_bearer_authHeader",
        "account_addresses": accounts,
        "transaction_types": raw.get("transactionTypes") or ["ANY"],
        "txn_status": raw.get("txnStatus") or "success",
        "receiver": "workbench_api POST /hooks/helius/solana",
        "alerts": [
            str(BASE / "solana_lock_alerts.jsonl"),
            str(BASE / "onchain_lock_alerts.jsonl"),
        ],
        "note": "API key and webhook secret are NOT stored in this file.",
    }
    save_state(doc)
    # Mark factories active
    try:
        fac = json.loads(FACTORIES.read_text(encoding="utf-8"))
    except Exception:
        fac = {}
    fac["updated_at"] = now_iso()
    fac["status"] = "helius_webhook_active"
    fac["helius_webhook_id"] = webhook_id
    fac["helius_watched_program_ids"] = accounts
    fac["todo"] = [
        "Receiver live at workbench /hooks/helius/solana",
        "Matched mints -> solana_lock_alerts.jsonl + onchain_lock_alerts.jsonl",
        "官网秒级CA快报 / ca-2 should also read solana_lock_alerts.jsonl",
        "Optional later: Raydium AMM V4/CPMM/CLMM (high swap volume — not wired)",
    ]
    FACTORIES.write_text(json.dumps(fac, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("ensure", "list", "delete", "status"):
        print("Usage: solana_helius_setup.py ensure [--force-mass]|list|delete|status")
        return 2
    cmd = sys.argv[1]
    if cmd == "ensure":
        return cmd_ensure(force_mass="--force-mass" in sys.argv[2:])
    if cmd == "list":
        return cmd_list()
    if cmd == "delete":
        return cmd_delete()
    if cmd == "status":
        pref = load_pref()
        st = load_state()
        print(json.dumps({
            "pref_mode": pref.get("mode"),
            "webhook_id": st.get("webhook_id"),
            "webhook_status": st.get("status") or ("active" if st.get("webhook_id") else "none"),
            "workbench_solana": workbench_solana_handles(),
            "receiver": "workbench_api POST /hooks/helius/solana",
        }, ensure_ascii=False, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
