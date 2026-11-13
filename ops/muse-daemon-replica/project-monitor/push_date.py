"""Canonical 推送日期 for a project card.

The earliest real "entered the radar / pushed to us" timestamp wins.
Launch times are not entry times and are ignored.

Field order (tie breaks toward the earlier name):
`push_date`, `first_seen`, `added_at`, `synced_at`, `created_at`, `date_iso`.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

ENTRY_FIELDS: Tuple[str, ...] = (
    "push_date",
    "first_seen",
    "added_at",
    "synced_at",
    "created_at",
    "date_iso",
)

_EMPTY = {"", "未知", "unknown", "null", "none", "n/a", "—", "-"}
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNIX = re.compile(r"^\d{10}(\d{3})?$")
_MIN = datetime(2015, 1, 1, tzinfo=timezone.utc)
_MAX = datetime(2100, 1, 1, tzinfo=timezone.utc)

Stamp = Tuple[int, str, str]  # epoch ms, original text, field name


def _camel(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _from_ms(ms: float, text: str) -> Optional[Tuple[int, str]]:
    if ms != ms:  # NaN
        return None
    whole = int(ms)
    dt = datetime.fromtimestamp(whole / 1000, timezone.utc)
    if dt < _MIN or dt >= _MAX:
        return None
    return whole, text


def parse_entry_time(value: Any) -> Optional[Tuple[int, str]]:
    """Return (epoch_ms, original_or_normalized_text) or None."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        ms = float(value) * 1000 if value < 1e12 else float(value)
        text = datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return _from_ms(ms, text)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() in _EMPTY:
        return None
    if _UNIX.fullmatch(text):
        raw = int(text)
        ms = raw * 1000 if len(text) == 10 else raw
        return _from_ms(ms, datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    if _DATE_ONLY.fullmatch(text):
        dt = datetime.fromisoformat(text + "T00:00:00+08:00")
        return int(dt.timestamp() * 1000), text
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if dt < _MIN or dt >= _MAX:
        return None
    return int(dt.timestamp() * 1000), text


def _read(record: Dict[str, Any], key: str) -> Any:
    if key in record and record.get(key) not in (None, ""):
        return record.get(key)
    camel = _camel(key)
    if camel in record and record.get(camel) not in (None, ""):
        return record.get(camel)
    return None


def canonical_push_date(*records: Any) -> str:
    """Original text of the earliest entry timestamp, or ""."""
    best: Optional[Stamp] = None
    best_priority = len(ENTRY_FIELDS)
    for record in records:
        if not isinstance(record, dict):
            continue
        for priority, key in enumerate(ENTRY_FIELDS):
            parsed = parse_entry_time(_read(record, key))
            if not parsed:
                continue
            stamp = (parsed[0], parsed[1], key)
            if best is None or stamp[0] < best[0] or (stamp[0] == best[0] and priority < best_priority):
                best = stamp
                best_priority = priority
    return best[1] if best else ""


def apply_push_date(row: Dict[str, Any], *earlier: Any) -> Dict[str, Any]:
    """Set `push_date` when any entry field parses. Leave the row unchanged otherwise."""
    stamp = canonical_push_date(row, *earlier)
    if stamp:
        row["push_date"] = stamp
    return row


def collapse_by_handle(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Keep the newest card per handle and stamp `first_seen` from the earliest push time.

    `date_iso` stays the newest Telegram message time. `first_seen` is the earliest
    `date_iso` / `first_seen` already stored on those cards. Projects are not dropped
    except for handle de-duplication, which the snapshot already did.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}
    order: List[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        handle = str(record.get("twitter_handle") or record.get("handle") or "").lstrip("@").lower()
        key = handle or f"msg:{record.get('message_id')}"
        if key not in groups:
            order.append(key)
            groups[key] = []
        groups[key].append(record)

    collapsed: List[Dict[str, Any]] = []
    for key in order:
        items = groups[key]
        newest = max(items, key=lambda item: _message_id(item))
        slim = {field: value for field, value in newest.items() if field != "raw_text"}
        first = canonical_push_date(*items)
        # first_seen is specifically the earliest card time, not a later synced_at.
        earliest_card = _earliest_card_time(items)
        if earliest_card:
            slim["first_seen"] = earliest_card
        elif first:
            slim["first_seen"] = first
        collapsed.append(slim)
    collapsed.sort(key=lambda item: _message_id(item), reverse=True)
    return collapsed


def _message_id(record: Dict[str, Any]) -> int:
    try:
        return int(record.get("message_id") or 0)
    except (TypeError, ValueError):
        return 0


def _earliest_card_time(items: Sequence[Dict[str, Any]]) -> str:
    """Earliest `date_iso` or already-stored `first_seen` among cards."""
    best: Optional[Tuple[int, str, int]] = None
    for record in items:
        for priority, key in enumerate(("first_seen", "date_iso")):
            parsed = parse_entry_time(_read(record, key))
            if not parsed:
                continue
            if best is None or parsed[0] < best[0] or (parsed[0] == best[0] and priority < best[2]):
                best = (parsed[0], parsed[1], priority)
    return best[1] if best else ""
