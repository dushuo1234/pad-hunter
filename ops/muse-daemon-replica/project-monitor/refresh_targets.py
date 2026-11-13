#!/usr/bin/env python3
"""Refresh targets.json from push-radar projects.json for 项目官网探活."""
from __future__ import annotations
import json, re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
from onchain_lock import load_launched_blocklist

BASE = Path('/workspace/project-monitor')
PROJECTS = Path('/workspace/push-radar/data/projects.json')
TARGETS = BASE / 'targets.json'
PREV = BASE / 'targets.prev.json'
STATS = BASE / '_targets_refresh_stats.json'
SH = ZoneInfo('Asia/Shanghai')

def is_truncated(u: str) -> bool:
    return (not u) or ('…' in u) or ('...' in u)

def host_of(u: str) -> str:
    try:
        return (urlparse(u).hostname or '').lower()
    except Exception:
        return ''

def is_x_only(u: str) -> bool:
    h = host_of(u)
    return h in ('x.com', 'twitter.com', 't.co') or h.endswith('.x.com') or h.endswith('.twitter.com')

def to_https(u: str) -> str:
    if u.lower().startswith('http://'):
        return 'https://' + u[7:]
    return u

def extract_sites(urls: list) -> tuple[list[str], int]:
    stripped = 0
    by_key: dict[tuple, str] = {}
    for u in urls or []:
        if not isinstance(u, str):
            continue
        u = u.strip()
        if is_truncated(u):
            stripped += 1
            continue
        if is_x_only(u):
            continue
        h = host_of(u)
        if not h:
            continue
        u = to_https(u)
        p = urlparse(u)
        key = (h, (p.path or '/').rstrip('/') or '/')
        # https already preferred via to_https; first wins unless replacing http leftover
        if key not in by_key:
            by_key[key] = u
    return list(by_key.values()), stripped

def main() -> int:
    blk = load_launched_blocklist()
    projects = json.loads(PROJECTS.read_text(encoding='utf-8'))
    old_targets = json.loads(TARGETS.read_text(encoding='utf-8')) if TARGETS.exists() else []
    PREV.write_text(json.dumps(old_targets, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    old_by = {(t.get('handle') or '').lstrip('@').lower(): t for t in old_targets}
    new_targets, added_handles, dropped_launched, dropped_orphans = [], [], [], []
    stripped_total, preserved_extra = 0, 0
    proj_handles = set()
    for p in projects:
        h = (p.get('twitter_handle') or '').lstrip('@').lower()
        if not h:
            continue
        proj_handles.add(h)
        if h in blk:
            if h in old_by:
                dropped_launched.append(h)
            continue
        card_sites, stripped = extract_sites(p.get('urls') or [])
        stripped_total += stripped
        old = old_by.get(h)
        sites = list(card_sites) if card_sites else []
        if not sites and old and old.get('sites'):
            sites, _ = extract_sites(old.get('sites') or [])
        if old and old.get('sites'):
            have = {(host_of(s), (urlparse(s).path or '/').rstrip('/') or '/') for s in sites}
            for s in old['sites']:
                if is_truncated(s) or is_x_only(s):
                    continue
                s2 = to_https(s)
                key = (host_of(s2), (urlparse(s2).path or '/').rstrip('/') or '/')
                if key not in have:
                    sites.append(s2)
                    have.add(key)
                    preserved_extra += 1
        entry = {
            'name': p.get('name') or (old or {}).get('name') or h,
            'handle': h,
            'x_url': p.get('x_url') or f'https://x.com/{h}',
            'sites': sites,
            'chain': p.get('chain') or '',
            'category': p.get('category') or '',
            'listing': p.get('listing') or '',
            'status': p.get('status') or '',
        }
        if h not in old_by:
            added_handles.append(h)
        new_targets.append(entry)
    for h in old_by:
        if h in proj_handles:
            continue
        if h in blk:
            if h not in dropped_launched:
                dropped_launched.append(h)
        else:
            dropped_orphans.append(h)
    TARGETS.write_text(json.dumps(new_targets, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    stats = {
        'refreshed_at': datetime.now(SH).strftime('%Y-%m-%d %H:%M Asia/Shanghai'),
        'old': len(old_targets),
        'new': len(new_targets),
        'added': len(added_handles),
        'added_handles': added_handles,
        'dropped_launched': dropped_launched,
        'dropped_orphans': dropped_orphans,
        'with_site': sum(1 for t in new_targets if t.get('sites')),
        'urls': sum(len(t.get('sites') or []) for t in new_targets),
        'blk': len(blk),
        'stripped_truncated': stripped_total,
        'preserved_extra': preserved_extra,
    }
    STATS.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
