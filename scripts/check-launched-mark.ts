import { applyServerBlocks, getBlockSnapshot, ingestBlocked, ingestLaunchNotice, launchedMarkBody, parseBlocklist, parseLaunchedMarkPayload, parseLaunchedRecent, releaseBlocked, siteClientIdFrom, withManualLaunched } from '../src/utils/launchedMark.ts'
import { sortLaunchedItems, type LaunchedItem } from '../src/utils/launched.ts'
import { retryAfterMs } from '../src/utils/workbenchApi.ts'

function fail(message: string): never {
  throw new Error(message)
}

if (siteClientIdFrom('abc') !== 'site-abc') fail('prefix device id')
if (siteClientIdFrom('site-abc') !== 'site-abc') fail('keep existing site prefix')

const body = launchedMarkBody({ handle: '@SomeHandle', name: '某项目', at: '2026-10-23T09:00:00.000Z', clientId: 'site-device' })
if (body.handle !== 'SomeHandle') fail('handle keeps case and strips @')
if (body.reason !== 'manual' || body.source !== 'manual') fail('reason and source')
if (body.client_id !== 'site-device') fail('client id')
if (body.name !== '某项目' || body.at !== '2026-10-23T09:00:00.000Z') fail('optional name and at')
const bare = launchedMarkBody({ handle: 'Only', clientId: 'site-device' })
if ('name' in bare || 'at' in bare) fail('omit empty optional fields')

const recent = parseLaunchedRecent({
  marks: [{ handle: '@Alpha', name: '甲', reason: 'manual', at: '2026-10-23T01:00:00.000Z' }],
})
if (!recent || recent.length !== 1 || recent[0]?.handle !== 'alpha') fail('recent marks normalize handle')

const block = parseBlocklist({
  manual_count: 1,
  manual_updated_at: '2026-10-23T01:00:00.000Z',
  handles: ['Beta'],
  items: [{ handle: 'Alpha', reason: 'manual', name: '甲' }],
})
if (!block || !block.handles.includes('alpha') || !block.handles.includes('beta')) fail(`blocklist handles ${block?.handles.join(',')}`)

const marked = parseLaunchedMarkPayload({
  ok: true,
  mark: { handle: 'Gamma', name: '丙', reason: 'manual', at: '2026-10-23T02:00:00.000Z' },
  already_blocked: false,
  blocklist_count: 3,
  dropped_launched: ['Gamma'],
  pins: { items: [], removed: [{ handle: 'Gamma', removed_at: '2026-10-23T02:00:00.000Z' }] },
  launched: { marks: [] },
  radar_removed: true,
})
if (!marked || !marked.marks.some((mark) => mark.handle === 'gamma')) fail('mark payload')
if (marked.pins == null) fail('pins passed through')

const archived = withManualLaunched(
  { count: 0, items: [] },
  [{ handle: 'gamma', name: '丙', reason: 'manual', at: '2026-10-23T02:00:00.000Z' }],
)
if (archived.items.length !== 1) fail('manual mark becomes a launched row')
if (archived.items[0]?.listingAt != null) fail('must not invent listing_at')
if (archived.items[0]?.project !== '丙') fail('launched name')

const skipped = withManualLaunched(
  {
    count: 1,
    items: [{
      project: '丙',
      handle: 'gamma',
      chain: '',
      category: '',
      xUrl: '',
      sites: [],
      listingAt: null,
      ca: null,
      caChain: null,
      reason: 'auto',
      evidence: '',
      removedAt: '2026-10-23T03:00:00.000Z',
    }],
  },
  [{ handle: 'Gamma', name: '丙', reason: 'manual', at: '2026-10-23T02:00:00.000Z' }],
)
if (skipped.items.length !== 1) fail('pages row already covers the handle')

if (retryAfterMs('1') !== 1000) fail('Retry-After 1 waits 1s')
if (retryAfterMs(null) !== 1000) fail('missing Retry-After waits 1s')
if (retryAfterMs('  ') !== 1000) fail('blank Retry-After waits 1s')
if (retryAfterMs('0') !== 0) fail('Retry-After 0')
if (retryAfterMs('90') !== 30_000) fail('Retry-After is capped at 30s')
if (retryAfterMs('soon') !== 1000) fail('unreadable Retry-After waits 1s')
const httpDate = 'Wed, 21 Oct 2015 07:28:00 GMT'
const httpAt = Date.parse(httpDate)
if (retryAfterMs(httpDate, httpAt - 2500) !== 2500) fail('Retry-After HTTP date')
if (retryAfterMs(httpDate, httpAt + 5000) !== 0) fail('past Retry-After does not wait')

ingestBlocked([{ handle: 'unmarkme', name: 'Un', reason: 'manual', at: '2026-10-23T04:00:00.000Z' }], true, 'recent')
ingestBlocked([{ handle: 'stayblock', name: 'Stay', reason: '', at: '' }], false, 'block')
ingestBlocked([{ handle: 'localonly', name: 'Local', reason: 'manual', at: '2026-10-23T04:00:00.000Z' }], true, 'local')
applyServerBlocks({
  recent: [],
  block: [{ handle: 'stayblock', name: 'Stay', reason: '', at: '' }],
})
const afterUnmark = getBlockSnapshot()
if (afterUnmark.handles.includes('unmarkme')) fail('empty recent list drops the unmarked handle')
if (!afterUnmark.handles.includes('stayblock')) fail('blocklist handle stays after recent unmark')
if (!afterUnmark.handles.includes('localonly')) fail('in-flight local mark stays until the server copy arrives')
if (afterUnmark.manual.some((mark) => mark.handle === 'unmarkme')) fail('unmarked handle leaves 已开盘')
applyServerBlocks({ recent: [], block: [] })
const cleared = getBlockSnapshot()
if (cleared.handles.includes('stayblock') || cleared.handles.includes('unmarkme')) fail('empty server lists clear server-sourced blocks')
if (!cleared.handles.includes('localonly')) fail('local mark still waits on POST')

ingestLaunchNotice([{ handle: '@SocketMark', name: '甲', reason: 'manual', at: '2026-10-23T05:00:00.000Z' }])
applyServerBlocks({ recent: [], block: [] })
const held = getBlockSnapshot()
if (!held.handles.includes('socketmark')) fail('socket mark waits for a list echo')
if (!held.manual.some((mark) => mark.handle === 'socketmark')) fail('socket manual mark is on 已开盘 before echo')
applyServerBlocks({
  recent: [{ handle: 'socketmark', name: '甲', reason: 'manual', at: '2026-10-23T05:00:00.000Z' }],
  block: [],
})
applyServerBlocks({ recent: [], block: [] })
if (getBlockSnapshot().handles.includes('socketmark')) fail('echoed mark leaves when the server list drops it')

ingestBlocked([{ handle: 'gone', name: '走', reason: 'manual', at: '2026-10-23T06:00:00.000Z' }], true, 'local')
releaseBlocked('@Gone')
if (getBlockSnapshot().handles.includes('gone')) fail('unmark drops the handle before refetch')

function launchedRow(partial: Partial<LaunchedItem> & Pick<LaunchedItem, 'handle' | 'project'>): LaunchedItem {
  return {
    chain: '',
    category: '',
    xUrl: '',
    sites: [],
    listingAt: null,
    ca: null,
    caChain: null,
    reason: '',
    evidence: '',
    removedAt: '',
    ...partial,
  }
}

const byPush = sortLaunchedItems([
  launchedRow({ handle: 'old', project: '旧', push_date: '2026-10-01T00:00:00Z', removedAt: '2026-10-23T00:00:00Z' }),
  launchedRow({ handle: 'fresh', project: '新', push_date: '2026-10-20T00:00:00Z', removedAt: '2026-10-02T00:00:00Z' }),
  launchedRow({ handle: 'blank', project: '无', removedAt: '2026-10-22T00:00:00Z' }),
])
if (byPush.map((item) => item.handle).join(',') !== 'fresh,old,blank') {
  fail(`launched order follows 推送日期, got ${byPush.map((item) => item.handle).join(',')}`)
}
const joined = sortLaunchedItems(
  [
    launchedRow({ handle: 'blank', project: '无', removedAt: '2026-10-23T00:00:00Z' }),
    launchedRow({ handle: 'fresh', project: '新', removedAt: '2026-01-01T00:00:00Z' }),
  ],
  (item) => [item, item.handle === 'blank' ? { push_date: '2026-10-21T00:00:00Z' } : undefined],
)
if (joined.map((item) => item.handle).join(',') !== 'blank,fresh') fail('catalog push date places a manual row')

console.log('launched mark checks ok')
