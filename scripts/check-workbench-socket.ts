import {
  isSocketAuthClose,
  parseSocketMessage,
  pinsSyncFrame,
  pongFrame,
  reviewedSyncFrame,
  workbenchWsUrl,
  wsBackoffMs,
} from '../src/utils/workbenchSocket.ts'

function fail(message: string): never {
  throw new Error(message)
}

const secure = new URL(workbenchWsUrl('https://pad.example/api/', 'tok en'))
if (secure.protocol !== 'wss:') fail(`expected wss, got ${secure.protocol}`)
if (secure.pathname !== '/api/v1/workbench/ws') fail(`path ${secure.pathname}`)
if (secure.searchParams.get('token') !== 'tok en') fail('token query was not preserved')

const plain = new URL(workbenchWsUrl('http://127.0.0.1:8799', 'a+b'))
if (plain.protocol !== 'ws:') fail(`expected ws, got ${plain.protocol}`)
if (plain.pathname !== '/v1/workbench/ws') fail(`root path ${plain.pathname}`)
if (plain.searchParams.get('token') !== 'a+b') fail('token encoding changed the value')

if (wsBackoffMs(0, 0) !== 1000) fail(`backoff 0 ${wsBackoffMs(0, 0)}`)
if (wsBackoffMs(1, 0) !== 2000) fail(`backoff 1 ${wsBackoffMs(1, 0)}`)
if (wsBackoffMs(2, 0) !== 4000) fail(`backoff 2 ${wsBackoffMs(2, 0)}`)
if (wsBackoffMs(5, 0) !== 30_000) fail(`backoff cap ${wsBackoffMs(5, 0)}`)
if (wsBackoffMs(0, 1) !== 1200) fail(`jitter ${wsBackoffMs(0, 1)}`)
if (wsBackoffMs(8, 1) !== 30_000) fail('jitter must not exceed 30s')

const hello = parseSocketMessage('{"type":"hello","version":3,"server_time":"2026-10-23T00:00:00.000Z"}')
if (hello.kind !== 'hello' || hello.version !== '3' || hello.serverTime !== '2026-10-23T00:00:00.000Z') fail('hello parse')

const pins = parseSocketMessage({
  type: 'pins',
  origin_client_id: 'other',
  state: {
    synced_at: '2026-10-23T00:00:00.000Z',
    items: [{ handle: 'Alpha', name: '甲', sites: ['https://a.example'], x_url: '', chain: 'solana', notes: 'n', push: true, added_at: '2026-10-01T00:00:00.000Z', updated_at: '2026-10-22T00:00:00.000Z' }],
    removed: [{ handle: 'Beta', removed_at: '2026-10-21T00:00:00.000Z' }],
  },
})
if (pins.kind !== 'pins') fail('pins kind')
if (pins.kind === 'pins') {
  if (pins.originClientId !== 'other') fail('origin')
  if (pins.state.items.length !== 1 || pins.state.items[0]?.handle !== 'Alpha') fail('pins items')
  if (pins.state.removed.length !== 1 || pins.state.removed[0]?.handle !== 'Beta') fail('pins tombstone')
}

const reviewed = parseSocketMessage({
  type: 'reviewed',
  origin_client_id: 'phone',
  state: {
    synced_at: '2026-10-23T00:00:00.000Z',
    marks: {
      Alpha: { at: '2026-10-22T00:00:00.000Z', cleared_at: '2026-10-23T00:00:00.000Z', snapshot: { listingAt: '2026-10-30T00:00:00+08:00', status: '', listing: '', ca: '' } },
    },
  },
})
if (reviewed.kind !== 'reviewed') fail('reviewed kind')
if (reviewed.kind === 'reviewed') {
  if (!reviewed.marks.alpha) fail('reviewed key should be lowercase')
  if (reviewed.marks.alpha?.cleared_at !== '2026-10-23T00:00:00.000Z') fail('cleared_at')
  if (reviewed.originClientId !== 'phone') fail('reviewed origin')
}

if (parseSocketMessage({ type: 'ping' }).kind !== 'ping') fail('ping')
if (pongFrame().type !== 'pong') fail('pong frame')
if (parseSocketMessage('not-json').kind !== 'ignore') fail('bad json should be ignored')
if (parseSocketMessage({ type: 'pins', state: { count: 1 } }).kind !== 'ignore') fail('legacy pin payload must not apply')
if (parseSocketMessage({ type: 'nope' }).kind !== 'ignore') fail('unknown type')

const pinFrame = pinsSyncFrame('me', {
  items: [{ handle: 'a', name: 'a', sites: [], x_url: '', chain: '', notes: '', push: true, added_at: '2026-10-01T00:00:00.000Z', updated_at: '2026-10-02T00:00:00.000Z' }],
  removed: [{ handle: 'b', removed_at: '2026-10-03T00:00:00.000Z' }],
})
if (pinFrame.type !== 'pins_sync' || pinFrame.body.client_id !== 'me' || pinFrame.body.removed.length !== 1) fail('pins_sync frame')

const reviewFrame = reviewedSyncFrame('me', {
  a: { at: '2026-10-02T00:00:00.000Z', cleared_at: '', snapshot: { listingAt: '', status: '', listing: '', ca: '' } },
})
if (reviewFrame.type !== 'reviewed_sync' || reviewFrame.body.client_id !== 'me' || !reviewFrame.body.marks.a) fail('reviewed_sync frame')

if (!isSocketAuthClose(4401)) fail('4401 is the bad-token close')
if (isSocketAuthClose(1006)) fail('network close is not an auth failure')

const dryRun = parseSocketMessage({
  type: 'workbench_alert',
  dry_run: true,
  origin_client_id: 'box-workbench-soon',
  alerts: [{ id: 'deadbeefdeadbeef', handle: 'CaravanRH', kind: 'ca', ca_status: 'confirmed', alert_ok: true }],
})
if (dryRun.kind !== 'ignore') fail('dry_run alert must be ignored')

const helloAlerts = parseSocketMessage({
  type: 'workbench_alerts',
  event: 'hello',
  state: {
    updated_at: '2026-10-24T00:01:00+08:00',
    count: 1,
    items: [{ id: 'aaaaaaaaaaaaaaa1', handle: '@CaravanRH', kind: 'x_post', ts: '2026-10-24T00:01:00+08:00', summary: '【甲】即将开始' }],
  },
})
if (helloAlerts.kind !== 'alerts_snapshot') fail('workbench_alerts hello')
if (helloAlerts.kind === 'alerts_snapshot' && (helloAlerts.alerts.length !== 1 || helloAlerts.alerts[0]?.handle !== 'CaravanRH')) {
  fail('hello alert handle')
}

const incremental = parseSocketMessage({
  type: 'workbench_alert',
  dry_run: false,
  alerts: [{ id: 'bbbbbbbbbbbbbbb1', handle: 'NftProj', kind: 'ca', ca_status: 'nft', alert_ok: false, summary: '不算' }],
})
if (incremental.kind !== 'alerts_incremental') fail('workbench_alert incremental')

console.log('workbench socket checks ok')
