#!/usr/bin/env python3
"""Checks for 推送日期 stamping. Does not write site data."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from push_date import apply_push_date, canonical_push_date, collapse_by_handle


def fail(message: str) -> None:
    raise SystemExit(message)


def main() -> None:
    row = apply_push_date(
        {
            "handle": "alpha",
            "date_iso": "2026-10-22T13:14:21+00:00",
            "listing_at": "2026-10-01T00:00:00+08:00",
            "fetched_at": "2026-10-19T00:00:00Z",
        },
        {"date_iso": "2026-10-18T01:02:03Z", "push_date": "2026-10-20T00:00:00Z"},
    )
    if row["push_date"] != "2026-10-18T01:02:03Z":
        fail(f"expected earliest previous card time, got {row['push_date']}")
    if row["date_iso"] != "2026-10-22T13:14:21+00:00":
        fail("date_iso must stay the newest card")
    if row.get("listing_at") != "2026-10-01T00:00:00+08:00":
        fail("listing_at must be left alone")

    blank = apply_push_date({"handle": "beta", "listing_at": "2026-10-27T21:00:00+08:00"})
    if "push_date" in blank:
        fail("listing_at must not be copied into push_date")

    collapsed = collapse_by_handle(
        [
            {"message_id": 1, "twitter_handle": "Same", "date_iso": "2026-10-01T00:00:00Z", "name": "old"},
            {"message_id": 9, "twitter_handle": "same", "date_iso": "2026-10-22T13:14:21+00:00", "name": "new", "raw_text": "drop"},
        ]
    )
    if len(collapsed) != 1:
        fail(f"expected one handle, got {len(collapsed)}")
    item = collapsed[0]
    if item["name"] != "new" or item["date_iso"] != "2026-10-22T13:14:21+00:00":
        fail("newest card should be kept")
    if item.get("first_seen") != "2026-10-01T00:00:00Z":
        fail(f"first_seen {item.get('first_seen')}")
    if "raw_text" in item:
        fail("raw_text leaked")
    if canonical_push_date(item) != "2026-10-01T00:00:00Z":
        fail("canonical push date should be first_seen")

    print("push date writer checks ok")


if __name__ == "__main__":
    main()
