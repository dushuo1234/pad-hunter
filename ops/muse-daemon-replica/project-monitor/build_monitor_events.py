#!/usr/bin/env python3
"""Turn scanner JSON into public/data/monitor_events.json.

Accepts the shapes Pad Hunter already renders:

- latest.json results[] — site up/down, http_code, time_s
- listing_scan_latest.json — new_listing_signals[], results[].sites/cas/signals
- watchlist.json projects[] — ca, ca_chain, ca_source, listing_signal

The page also reads those documents directly if you paste them into
monitor_events.json under latest / listing_scan / watchlist, or replace the
file with one raw document. This script writes the normalized events array.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def load(path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None
    file = Path(path)
    if not file.exists():
        raise SystemExit(f"missing {file}")
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"expected an object in {file}")
    return data


def stamp(kind: str, handle: str, at: str, extra: str) -> str:
    return "|".join(part for part in (kind, handle.lower(), at, extra) if part)


def site_status(row: Dict[str, Any]) -> str:
    status = str(row.get("status") or "").strip()
    if status:
        return status
    if row.get("ok") is True:
        return "up"
    if row.get("ok") is False:
        return "down"
    return ""


def add_site(events: List[Dict[str, Any]], seen: set, row: Dict[str, Any], handle: str, name: str, at: str) -> None:
    url = str(row.get("url") or "").strip()
    if not url or not handle:
        return
    if row.get("http_code") is None and row.get("status") is None and row.get("time_s") is None and row.get("ok") is None:
        return
    event_id = stamp("site", handle, at, url)
    key = ("site", handle.lower(), url, at, site_status(row), row.get("time_s"))
    if key in seen:
        return
    seen.add(key)
    site = {
        "url": url,
        "status": site_status(row),
        "http_code": "" if row.get("http_code") is None else str(row.get("http_code")),
        "time_s": row.get("time_s"),
        "final_url": row.get("final_url") or "",
        "error": row.get("error") or "",
        "name": name,
        "handle": handle,
    }
    if isinstance(row.get("ok"), bool):
        site["ok"] = row["ok"]
    events.append(
        {
            "id": event_id,
            "kind": "site",
            "at": at,
            "handle": handle,
            "name": name,
            "site": site,
        }
    )


def add_signal(events: List[Dict[str, Any]], seen: set, handle: str, name: str, at: str, signal: str, extra: Optional[Dict[str, Any]] = None) -> None:
    text = signal.strip()
    if not handle or not text:
        return
    key = ("sig", handle.lower(), text)
    if key in seen:
        return
    seen.add(key)
    payload: Dict[str, Any] = {
        "name": name,
        "handle": handle,
        "signal": text,
        "prev": None if not extra else extra.get("prev"),
    }
    if extra:
        if extra.get("keyword"):
            payload["keyword"] = extra["keyword"]
        if extra.get("source"):
            payload["source"] = extra["source"]
    events.append(
        {
            "id": stamp("listing_signal", handle, "", text[:120]),
            "kind": "listing_signal",
            "at": at,
            "handle": handle,
            "name": name,
            "listing_signal": payload,
        }
    )


def add_ca(events: List[Dict[str, Any]], seen: set, handle: str, name: str, at: str, ca: str, chain: str = "", source: str = "", sample: bool = False, note: str = "") -> None:
    text = ca.strip()
    if not handle or not text:
        return
    key = ("ca", handle.lower(), text)
    if key in seen:
        return
    seen.add(key)
    event: Dict[str, Any] = {
        "id": stamp("ca", handle, at, text),
        "kind": "ca",
        "at": at,
        "handle": handle,
        "name": name,
        "ca": text,
        "ca_chain": chain or None,
        "ca_source": source or None,
    }
    if sample:
        event["sample"] = True
    if note:
        event["note"] = note
    events.append(event)


def from_latest(doc: Dict[str, Any], events: List[Dict[str, Any]], seen: set) -> None:
    at_fallback = str(doc.get("checked_at_iso") or doc.get("checked_at") or "")
    for row in doc.get("results") or []:
        if not isinstance(row, dict):
            continue
        add_site(
            events,
            seen,
            row,
            str(row.get("handle") or ""),
            str(row.get("name") or ""),
            str(row.get("checked_at") or at_fallback),
        )


def from_listing(doc: Dict[str, Any], events: List[Dict[str, Any]], seen: set) -> None:
    at_fallback = str(doc.get("checked_at_iso") or doc.get("checked_at") or "")
    for row in doc.get("new_listing_signals") or []:
        if not isinstance(row, dict):
            continue
        add_signal(
            events,
            seen,
            str(row.get("handle") or ""),
            str(row.get("name") or ""),
            at_fallback,
            str(row.get("signal") or ""),
            {"prev": row.get("prev")},
        )
    for row in doc.get("new_cas") or []:
        if isinstance(row, str):
            continue
        if not isinstance(row, dict):
            continue
        ca = str(row.get("ca") or row.get("address") or "")
        add_ca(
            events,
            seen,
            str(row.get("handle") or ""),
            str(row.get("name") or ""),
            at_fallback,
            ca,
            str(row.get("ca_chain") or row.get("chain") or ""),
            str(row.get("ca_source") or row.get("source") or ""),
        )
    for row in doc.get("results") or []:
        if not isinstance(row, dict):
            continue
        handle = str(row.get("handle") or "")
        name = str(row.get("name") or "")
        at = str(row.get("checked_at") or at_fallback)
        for site in row.get("sites") or []:
            if isinstance(site, dict):
                add_site(events, seen, site, handle, name, at)
        signal = row.get("listing_signal")
        if isinstance(signal, str):
            add_signal(events, seen, handle, name, at, signal, {"prev": None})
        for item in row.get("signals") or []:
            if not isinstance(item, dict):
                continue
            add_signal(
                events,
                seen,
                handle,
                name,
                at,
                str(item.get("snippet") or item.get("signal") or ""),
                {"keyword": item.get("keyword"), "source": item.get("source"), "prev": None},
            )
        for item in row.get("cas") or []:
            if isinstance(item, str):
                add_ca(events, seen, handle, name, at, item)
            elif isinstance(item, dict):
                add_ca(
                    events,
                    seen,
                    handle,
                    name,
                    at,
                    str(item.get("ca") or item.get("address") or ""),
                    str(item.get("ca_chain") or item.get("chain") or ""),
                    str(item.get("ca_source") or item.get("source") or ""),
                )
        primary = row.get("primary_ca")
        if isinstance(primary, str):
            add_ca(events, seen, handle, name, at, primary, str(row.get("ca_chain") or ""), str(row.get("ca_source") or ""))


def from_watchlist(doc: Dict[str, Any], events: List[Dict[str, Any]], seen: set) -> None:
    for row in doc.get("projects") or []:
        if not isinstance(row, dict):
            continue
        handle = str(row.get("handle") or "")
        name = str(row.get("name") or "")
        at = str(row.get("last_checked") or row.get("locked_at") or "")
        ca = row.get("ca")
        if isinstance(ca, str) and ca.strip():
            add_ca(
                events,
                seen,
                handle,
                name,
                at,
                ca,
                str(row.get("ca_chain") or ""),
                str(row.get("ca_source") or ""),
            )
        signal = row.get("listing_signal")
        if isinstance(signal, str):
            add_signal(events, seen, handle, name, at, signal, {"prev": None})


def sample_events() -> List[Dict[str, Any]]:
    at = "2026-10-20T11:14:08+08:00"
    return [
        {
            "id": "ca|privatekeycoin_|sample",
            "kind": "ca",
            "at": at,
            "handle": "PrivateKeyCoin_",
            "name": "$PKC",
            "sample": True,
            "note": "示例 CA，不是链上结果。接入真实扫描后删除。",
            "ca": "0xSAMPLE0000000000000000000000000000pkc",
            "ca_chain": "unknown",
            "ca_source": "sample",
        },
        {
            "id": "factory|hypeqfun|sample",
            "kind": "factory",
            "at": at,
            "handle": "hypeqfun",
            "name": "HypeQ",
            "sample": True,
            "note": "示例工厂部署，不是链上结果。",
            "factory_deploy": {
                "chain": "hyperevm",
                "tx": "0xSAMPLETX000000000000000000000000000000000000000000000000000000000001",
                "factory": "0xSAMPLEFACTORY0000000000000000000000000001",
                "token": "0xSAMPLE0000000000000000000000000000000001",
                "block": None,
                "notes": "示例：链上工厂部署。接入真实扫描后替换。",
                "name": "HypeQ",
                "handle": "hypeqfun",
            },
        },
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build Pad Hunter monitor_events.json")
    ap.add_argument("--latest", help="latest.json from the site probe")
    ap.add_argument("--listing-scan", help="listing_scan_latest.json")
    ap.add_argument("--watchlist", help="watchlist.json")
    ap.add_argument("--samples", action="store_true", help="append clearly marked demo CA and factory events")
    ap.add_argument("--out", required=True, help="output path")
    args = ap.parse_args()

    events: List[Dict[str, Any]] = []
    seen: set = set()
    latest = load(args.latest)
    listing = load(args.listing_scan)
    watchlist = load(args.watchlist)
    if latest:
        from_latest(latest, events, seen)
    if listing:
        from_listing(listing, events, seen)
    if watchlist:
        from_watchlist(watchlist, events, seen)
    if args.samples:
        for event in sample_events():
            events.append(event)

    events.sort(key=lambda event: event.get("at") or "", reverse=True)
    generated = None
    for doc in (listing, latest, watchlist):
        if not doc:
            continue
        generated = doc.get("checked_at_iso") or doc.get("generated_at") or doc.get("locked_at")
        if generated:
            break
    payload = {
        "generated_at": generated or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "note": "监控事件按 handle 归到项目时间线。kind 为 site / listing_signal / ca / factory。sample=true 的行只在时间线展示，不计入当前 CA。可直接追加 events，或把扫描器原文放在 latest、listing_scan、watchlist、factory_deploys。",
        "events": events,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"events: {len(events)} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
