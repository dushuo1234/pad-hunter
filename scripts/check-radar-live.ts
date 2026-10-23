import { compareCandidates } from '../src/utils/candidates.ts'
import { upcomingLaunches } from '../src/utils/launch.ts'
import { pushDateMillis } from '../src/utils/pushDate.ts'
import { applyRadarDelta, applyRadarSnapshot, coerceRadarCard, getRadarOverlay, mergeRadarCards, readRadarCards } from '../src/utils/radarLive.ts'
import type { Candidate } from '../src/types/index.ts'

function fail(message: string): never {
  throw new Error(message)
}

function card(partial: Partial<Candidate> & Pick<Candidate, 'handle' | 'name'>): Candidate {
  return {
    rank: 1,
    followers: 0,
    kol_followers: 0,
    bio: '',
    why: '',
    score: 0,
    tweet_url: '',
    chain: 'BSC',
    ...partial,
  }
}

const older = card({ handle: 'Alpha', name: '旧', why: '保留简介', date_iso: '2026-10-01T00:00:00Z', push_date: '2026-10-01T00:00:00Z', listing_at: '2026-10-20T00:00:00+08:00' })
const newerThin = coerceRadarCard({
  handle: '@alpha',
  name: '新名',
  why: '',
  status: '即将启动',
  pushed_at: '2026-10-23T09:00:00Z',
  site: 'https://alpha.example',
  listing_at: null,
})
if (!newerThin) fail('coerce')
const merged = mergeRadarCards([older], [newerThin])
if (merged.length !== 1) fail(`merge count ${merged.length}`)
if (merged[0]?.name !== '新名') fail('newer name wins')
if (merged[0]?.why !== '保留简介') fail('empty why must not wipe the static card')
if (merged[0]?.listing_at !== '2026-10-20T00:00:00+08:00') fail('null listing_at must not invent or erase a time')
if (merged[0]?.push_date !== '2026-10-01T00:00:00Z') fail('earlier push date stays')
if (!merged[0]?.sites?.includes('https://alpha.example')) fail('site should land on sites')

const stale = coerceRadarCard({ handle: 'alpha', name: '更旧', pushed_at: '2026-09-01T00:00:00Z', why: '不要盖' })
if (!stale) fail('stale coerce')
const kept = mergeRadarCards(merged, [stale])
if (kept[0]?.name !== '新名' || kept[0]?.why === '不要盖') fail('older push must not replace')

const fresh = coerceRadarCard({ handle: 'brandnew', name: '刚推', pushed_at: '2026-10-23T10:00:00Z', chain: 'SOL' })
if (!fresh) fail('fresh')
const board = mergeRadarCards(kept, [fresh])
const sorted = [...board].sort(compareCandidates('date'))
if (sorted[0]?.handle.toLowerCase() !== 'brandnew') fail(`newest push should be first, got ${sorted.map((item) => item.handle).join(',')}`)
if (sorted.at(-1)?.handle.toLowerCase() !== 'alpha') fail('older push date stays below the new card')

const undated = card({ handle: 'nodate', name: '无日期', rank: 1 })
const dated = card({ handle: 'dated', name: '有', rank: 9, push_date: '2026-10-02T00:00:00Z' })
const order = [undated, dated].sort(compareCandidates('date')).map((item) => item.handle)
if (order.join(',') !== 'dated,nodate') fail(`missing push date should sink, got ${order.join(',')}`)
if (pushDateMillis([undated]) !== 0) fail('missing push date millis')

const recent = readRadarCards({ synced_at: '2026-10-23T00:00:00Z', cards: [{ handle: 'FromApi', name: '接口', pushed_at: '2026-10-23T08:00:00Z' }] })
if (recent.length !== 1 || recent[0]?.date_iso !== '2026-10-23T08:00:00Z') fail('recent cards copy pushed_at onto date_iso')

applyRadarSnapshot([{ handle: 'snap', name: '快照', pushed_at: '2026-10-23T01:00:00Z' }])
applyRadarDelta([{ handle: 'delta', name: '增量', pushed_at: '2026-10-23T02:00:00Z' }])
const overlay = getRadarOverlay().map((item) => item.handle.toLowerCase())
if (overlay.join(',') !== 'snap,delta') fail(`overlay ${overlay.join(',')}`)

const now = new Date('2026-10-22T08:00:00+08:00')
const tie = upcomingLaunches(
  [
    card({ handle: 'tieOld', name: '旧开盘', listing_at: '2026-10-23T12:00:00+08:00', status: '开发中', listing: '未开盘', push_date: '2026-10-01T00:00:00Z' }),
    card({ handle: 'tieNew', name: '新开盘', listing_at: '2026-10-23T12:00:00+08:00', status: '开发中', listing: '未开盘', push_date: '2026-10-21T00:00:00Z' }),
  ],
  [],
  [],
  now,
)
if (tie.map((row) => row.candidate.handle).join(',') !== 'tieNew,tieOld') fail('same listing time breaks ties by push date')

console.log('radar live checks ok')
