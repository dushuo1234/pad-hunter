#!/usr/bin/env python3
"""Telegram bot123123: ONLY 今日项目清单 digest + CA for handles currently on that list.

Hard rule (adu 2026-10-28): never push unrelated Pad Hunter / 柳叶刀 / global CA here.
CA quality (adu via 阿杜/炼油 2026-10-28):
  - 代币 only: is_token / kind=token (ca_gate.verify_address)
  - 固定CA only: ① deployer/related wallet OR ② official X
  - Site scrape / pure high-conf candidate / prior TG alone → 待确认, do NOT push
  - Example: Fishesrh 0x098e…9dbf is candidate — never treat as fixed
"""
from __future__ import annotations
import html
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
TZ = ZoneInfo("Asia/Shanghai")
TOKEN_FILE = BASE / "secrets" / "telegram_bot_token"
CHAT_FILE = BASE / "secrets" / "telegram_today_chat.json"
TODAY = BASE / "today_projects.json"
CA_FINDS = BASE / "ca_finds.json"
CA_STATE = BASE / "alerts" / "today_projects_tg_ca_state.json"


def load_json(p: Path, d=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return d if d is not None else {}


def norm(h) -> str:
    return (h or "").lstrip("@").strip().lower()


def today_handles() -> set[str]:
    doc = load_json(TODAY, {})
    out = set()
    for it in doc.get("items") or []:
        if isinstance(it, dict) and it.get("handle"):
            out.add(norm(it["handle"]))
    return out


def is_today_handle(handle: str) -> bool:
    return norm(handle) in today_handles()


def chat_id() -> int:
    return int(load_json(CHAT_FILE, {})["chat_id"])


def token() -> str:
    return TOKEN_FILE.read_text(encoding="utf-8").strip()


def send_html(text: str) -> dict:
    body = urllib.parse.urlencode(
        {
            "chat_id": chat_id(),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token()}/sendMessage", data=body, method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _find_for(handle: str, ca: str) -> dict | None:
    doc = load_json(CA_FINDS, {})
    hl, cl = norm(handle), (ca or "").lower()
    buckets = []
    if isinstance(doc, dict):
        buckets.extend(doc.get("finds") or [])
        buckets.extend(doc.get("suspected_copycats") or [])
        buckets.extend(doc.get("ca_locked_projects") or [])
    for f in buckets:
        if not isinstance(f, dict):
            continue
        if norm(f.get("handle")) == hl and (f.get("address") or "").lower() == cl:
            return f
    return None


def push_ca(
    *,
    handle: str,
    name: str | None = None,
    ca: str,
    chain: str | None = None,
    kind: str = "ca",
    summary: str | None = None,
    listing_at: str | None = None,
    site: str | None = None,
    force: bool = False,
    find: dict | None = None,
    official_x: bool | None = None,
    wallet_factory: bool | None = None,
    skip_verify: bool = False,
) -> dict:
    """Push one CA alert. Refuses unless handle is on today_projects (unless force for tests).

    Also refuses unless 固定CA (official_x OR deployer/related) AND token-shaped,
    unless force=True (tests only).
    """
    hl = norm(handle)
    if not force and not is_today_handle(hl):
        return {"ok": False, "skipped": "not_on_today_list", "handle": hl}
    # 2026-10-29 Capta: denied CA / personal-KOL handle never reach bot123123
    if not force:
        try:
            from ca_confidence import denied_ca, non_project_account
            if denied_ca(ca):
                return {"ok": False, "skipped": "denied_ca", "handle": hl, "ca": ca}
            _np, _why = non_project_account(hl)
            if _np:
                return {"ok": False, "skipped": "kol_not_official", "reason": _why, "handle": hl, "ca": ca}
        except Exception:
            pass

    find = find if isinstance(find, dict) else _find_for(hl, ca) or {}
    if wallet_factory is True and not find.get("wallet_factory_confirmed"):
        find = {**find, "wallet_factory_confirmed": True}

    # Hard refuse suspected copycats / not_ca even if caller passed find=
    if not force:
        st_ca = str(find.get("ca_status") or "").lower()
        if find.get("suspected_copycat") or st_ca in ("suspected_copycat", "not_ca", "superseded"):
            return {
                "ok": False,
                "skipped": "suspected_copycat" if "copycat" in st_ca or find.get("suspected_copycat") else st_ca or "suspected_copycat",
                "handle": hl,
                "ca": ca,
            }

    # Token gate
    if not force and not skip_verify:
        try:
            from ca_gate import verify_address
            v = verify_address(ca, chain or find.get("chain"), source=find.get("source"))
        except Exception as e:
            v = {"is_token": False, "kind": "unknown", "note": f"verify_err:{e}"[:120]}
        kind_v = str(v.get("kind") or find.get("kind") or "").lower()
        is_tok = bool(v.get("is_token")) or kind_v == "token" or bool(find.get("is_token"))
        if kind_v in ("nft", "hybrid", "hybrid_404", "wallet") or not is_tok:
            return {
                "ok": False,
                "skipped": "not_token",
                "handle": hl,
                "ca": ca,
                "verify": {"kind": v.get("kind"), "is_token": v.get("is_token"), "note": v.get("note")},
            }

    # 固定CA gate
    if not force:
        try:
            from ca_confidence import is_ca_fixed
            fixed, why = is_ca_fixed(
                find,
                official_x=True if official_x else (None if official_x is None else False),
                handle=hl,
                source=find.get("source"),
                post_url=find.get("official_x_url") or find.get("evidence_url"),
            )
            if wallet_factory is True and not fixed:
                fixed, why = True, "deployer_or_related"
        except Exception as e:
            # fail closed if helper unavailable and no explicit official flag
            if official_x or wallet_factory or (find.get("official_x_confirmed") or find.get("wallet_factory_confirmed")):
                fixed, why = True, "caller_flag_or_find"
            else:
                fixed, why = False, f"fixed_check_err:{e}"[:80]
        if not fixed:
            return {
                "ok": False,
                "skipped": "not_fixed_ca",
                "reason": why,
                "handle": hl,
                "ca": ca,
            }

    st = load_json(CA_STATE, {})
    dedupe_key = f"{hl}|{(ca or '').lower()}|{kind}"
    if not force and st.get("last", {}).get(dedupe_key):
        return {"ok": True, "skipped": "deduped", "handle": hl, "ca": ca}

    title = "🎯 今日清单 · 固定CA" if kind != "launched" else "✅ 今日清单 · 官推固定CA已开盘"
    lines = [
        f"<b>{html.escape(title)}</b>",
        f"• <b>{html.escape(name or hl)}</b> @{html.escape(hl)}",
        f"• CA：<code>{html.escape(ca)}</code>" + (f" · {html.escape(chain)}" if chain else ""),
    ]
    if listing_at:
        lines.append(f"• 开盘：{html.escape(str(listing_at))} Asia/Shanghai")
    if summary:
        lines.append(f"• {html.escape(summary[:200])}")
    if site:
        lines.append(f"• {html.escape(site)}")
    text = "\n".join(lines)
    res = send_html(text)
    ok = bool(res.get("ok"))
    if ok:
        last = st.setdefault("last", {})
        last[dedupe_key] = {
            "at": datetime.now(TZ).isoformat(timespec="seconds"),
            "message_id": (res.get("result") or {}).get("message_id"),
        }
        if len(last) > 500:
            for k in list(last.keys())[: len(last) - 500]:
                last.pop(k, None)
        CA_STATE.parent.mkdir(parents=True, exist_ok=True)
        CA_STATE.write_text(json.dumps(st, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "ok": ok,
        "handle": hl,
        "ca": ca,
        "message_id": (res.get("result") or {}).get("message_id"),
        "error": None if ok else res,
    }
