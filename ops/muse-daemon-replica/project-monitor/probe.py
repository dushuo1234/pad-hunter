#!/usr/bin/env python3
"""Probe Pad Hunter project websites; write latest.json and print a short digest."""
from __future__ import annotations
import json, subprocess, time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path('/workspace/project-monitor')
TARGETS = BASE / 'targets.json'
LATEST = BASE / 'latest.json'
PREV = BASE / 'previous.json'
SH = ZoneInfo('Asia/Shanghai')
UA = 'Mozilla/5.0 (compatible; PadHunterMonitor/1.0)'

def probe(url: str) -> dict:
    t0 = time.time()
    try:
        out = subprocess.run(
            ['curl','-sS','-o','/dev/null','-w','%{http_code}|%{time_total}|%{url_effective}','-L','--max-time','25','-A',UA,url],
            capture_output=True, text=True, timeout=35,
        )
        body = (out.stdout or '').strip()
        err = (out.stderr or '').strip()[:240]
        parts = body.split('|') if body else []
        code = parts[0] if parts else '000'
        ttot = float(parts[1]) if len(parts) > 1 and parts[1] else round(time.time()-t0, 3)
        final = parts[2] if len(parts) > 2 else url
        ok = code.isdigit() and 200 <= int(code) < 400
        return {'url': url, 'status': 'up' if ok else 'down', 'http_code': code, 'time_s': round(ttot, 3), 'final_url': final, 'error': '' if ok else (err or f'curl exit {out.returncode}')}
    except Exception as e:
        return {'url': url, 'status': 'down', 'http_code': '000', 'time_s': round(time.time()-t0, 3), 'final_url': url, 'error': str(e)[:240]}

def main() -> int:
    targets = json.loads(TARGETS.read_text(encoding='utf-8'))
    try:  # never probe/alert 已开盘 projects
        from onchain_lock import load_launched_blocklist
        _blk = load_launched_blocklist()
        targets = [x for x in targets if (x.get('handle') or '').lstrip('@').lower() not in _blk]
    except Exception:
        pass
    prev = {}
    if PREV.exists():
        try:
            prev = {(r['name'], r['url']): r for r in json.loads(PREV.read_text(encoding='utf-8')).get('results', [])}
        except Exception:
            prev = {}
    results = []
    for t in targets:
        for url in t.get('sites') or []:
            r = probe(url)
            r.update({'name': t['name'], 'handle': t.get('handle')})
            results.append(r)
            print(f"{r['status']:4} {r['http_code']:>3} {r['time_s']:6.2f}s  {t['name']}  {url}")
    report = {
        'checked_at': datetime.now(SH).strftime('%Y-%m-%d %H:%M:%S Asia/Shanghai'),
        'projects_total': len(targets),
        'with_site': sum(1 for t in targets if t.get('sites')),
        'without_site': [t['name'] for t in targets if not t.get('sites')],
        'results': results,
    }
    if LATEST.exists():
        PREV.write_text(LATEST.read_text(encoding='utf-8'), encoding='utf-8')
    LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    changes = []
    for r in results:
        key = (r['name'], r['url'])
        old = prev.get(key)
        if old and old.get('status') != r['status']:
            changes.append(f"{r['name']} {old.get('status')}→{r['status']} ({r['url']})")
    downs = [r for r in results if r['status'] == 'down']
    ups = [r for r in results if r['status'] == 'up']
    print(f"SUMMARY up={len(ups)} down={len(downs)} changes={len(changes)} no_site={len(report['without_site'])}")
    for c in changes:
        print('CHANGE', c)
    for d in downs:
        print('DOWN', d['name'], d['url'], d.get('error','')[:80])
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
