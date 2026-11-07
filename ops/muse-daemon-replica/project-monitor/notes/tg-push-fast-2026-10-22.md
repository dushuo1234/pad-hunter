# Near-realtime TG → Pad Hunter (2026-10-22 Asia/Shanghai)

## Latency path (before)
1. Routine 项目推送监控 every **30m** → fetch (~20–25s) → merge (<0.1s) → dual publish (~10–20s)
2. GitHub Pages CDN `Cache-Control: max-age=600` → up to **~10 min** extra after publish
3. Frontend loaded candidates **once** on mount (`cache: 'no-cache'` still hits varnish)

End-to-end: **30–40+ minutes** worst case.

## Latency path (after)
1. **Daemon** `tg_push_fast` every **60s** (flock on `tg.fetch.lock`):
   - Telethon fetch limit=40 (~14–25s)
   - `sync_site --offline` + `merge_projects_into_candidates` (<0.1s)
   - On new cards only: `publish_radar_data` → main `public/data/*` + gh-pages `data/*` (~10–20s)
2. **Live API** (workbench v1.3.0, ngrok): `GET /v1/radar/candidates|projects|launched|meta` — no token, `Cache-Control: no-store`
3. **Frontend PR #33**: soft-poll every 20s + focus/visibility; prefer live API, else Pages with `?t=` bust

Expected visible latency with PR #33 merged: **~20–80s** after a TG card posts (daemon interval + fetch + poll).
Without PR #33 (Pages CDN only): publish is fast, but CDN can still lag up to ~10 min.

## Verify
```bash
/workspace/project-monitor/tg_push_fast_daemon.sh status
curl -s http://127.0.0.1:8780/v1/radar/meta | jq .
curl -s -H 'ngrok-skip-browser-warning: 1' \
  https://dotted-disengage-awoke.ngrok-free.dev/v1/radar/meta | jq .
tail -50 /workspace/project-monitor/tg_push_fast.log
```

## Safety net
Keep 项目推送监控 @ 30m for digests / full board. Daemon owns near-realtime publish.
Sticky `push_date` unchanged. CA gate untouched. TapeRobot stays finished.
