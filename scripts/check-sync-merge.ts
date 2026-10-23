import {
  canonicalPinState,
  isReviewedActive,
  mergePins,
  mergeReviewed,
  parsePinResponse,
  parseReviewResponse,
  pinsNeedPush,
  reviewsNeedPush,
  withDroppedHandles,
  type PinMergeState,
  type PinWire,
  type ReviewWire,
} from '../src/utils/syncMerge.ts'

function fail(message: string): never {
  throw new Error(message)
}

function pin(handle: string, updatedAt: string, extra: Partial<PinWire> = {}): PinWire {
  return {
    handle,
    name: extra.name ?? handle,
    sites: extra.sites ?? [`https://${handle}.example`],
    x_url: extra.x_url ?? `https://x.com/${handle}`,
    chain: extra.chain ?? 'solana',
    notes: extra.notes ?? '',
    push: extra.push ?? true,
    added_at: extra.added_at ?? '2026-10-01T00:00:00.000Z',
    updated_at: updatedAt,
  }
}

function tomb(handle: string, removedAt: string) {
  return { handle, removed_at: removedAt }
}

function state(items: PinWire[], removed: PinMergeState['removed'] = []): PinMergeState {
  return { items, removed }
}

function mark(at: string, cleared = '', listingAt = ''): ReviewWire {
  return {
    at,
    cleared_at: cleared,
    snapshot: { listingAt, status: '即将启动', listing: '未开盘', ca: '' },
  }
}

const desktop = pin('Alpha', '2026-10-20T01:00:00.000Z', { notes: '桌面备注' })
const phoneEmpty = state([])
const desktopBoard = state([desktop])

const merged = mergePins(phoneEmpty, desktopBoard)
if (merged.items.length !== 1 || merged.items[0]?.notes !== '桌面备注') fail('empty phone must keep desktop pins')
if (pinsNeedPush(phoneEmpty, desktopBoard)) fail('empty phone must not push a replace over desktop pins')

const phoneNewer = pin('alpha', '2026-10-21T01:00:00.000Z', { notes: '手机备注' })
const phoneWins = mergePins(state([phoneNewer]), desktopBoard)
if (phoneWins.items.length !== 1 || phoneWins.items[0]?.notes !== '手机备注') fail('newer phone notes should win')
if (!pinsNeedPush(state([phoneNewer]), desktopBoard)) fail('newer phone pin should push')

const desktopNewer = pin('Alpha', '2026-10-22T01:00:00.000Z', { notes: '更新的桌面' })
const remoteWins = mergePins(state([phoneNewer]), state([desktopNewer]))
if (remoteWins.items[0]?.notes !== '更新的桌面') fail('newer remote pin should win')
if (pinsNeedPush(state([phoneNewer]), state([desktopNewer]))) fail('older local pin must not push')

const removed = mergePins(
  state([pin('alpha', '2026-10-20T01:00:00.000Z')]),
  state([], [tomb('Alpha', '2026-10-23T01:00:00.000Z')]),
)
if (removed.items.length !== 0 || removed.removed.length !== 1) fail('newer tombstone removes the pin')

const repinned = mergePins(
  state([pin('alpha', '2026-10-24T01:00:00.000Z', { notes: '重新钉选' })]),
  state([], [tomb('alpha', '2026-10-23T01:00:00.000Z')]),
)
if (repinned.items.length !== 1 || repinned.removed.length !== 0) fail('newer pin beats an older tombstone')

const tie = mergePins(
  state([pin('alpha', '2026-10-23T01:00:00.000Z', { notes: '同刻' })]),
  state([], [tomb('alpha', '2026-10-23T01:00:00.000Z')]),
)
if (tie.items.length !== 1) fail('equal updated_at and removed_at keeps the pin')

const both = mergePins(
  state([pin('alpha', '2026-10-20T00:00:00.000Z')]),
  state([pin('beta', '2026-10-20T00:00:00.000Z')]),
)
if (both.items.map((item) => item.handle.toLowerCase()).join(',') !== 'alpha,beta') fail('disjoint handles union')

const tieContent = mergePins(
  state([pin('alpha', '2026-10-20T00:00:00.000Z', { notes: 'local' })]),
  state([pin('alpha', '2026-10-20T00:00:00.000Z', { notes: 'remote' })]),
)
if (tieContent.items[0]?.notes !== 'remote') fail('equal timestamps prefer remote so devices converge')
if (pinsNeedPush(
  state([pin('alpha', '2026-10-20T00:00:00.000Z', { notes: 'local' })]),
  state([pin('alpha', '2026-10-20T00:00:00.000Z', { notes: 'remote' })]),
)) fail('timestamp tie must not push local content')

const localTomb = mergePins(
  state([], [tomb('alpha', '2026-10-25T00:00:00.000Z')]),
  state([pin('alpha', '2026-10-20T00:00:00.000Z')]),
)
if (localTomb.items.length !== 0) fail('local tombstone newer than remote pin removes it')
if (!pinsNeedPush(state([], [tomb('alpha', '2026-10-25T00:00:00.000Z')]), state([pin('alpha', '2026-10-20T00:00:00.000Z')]))) {
  fail('local tombstone should push')
}

if (canonicalPinState(desktopBoard) !== canonicalPinState(mergePins(phoneEmpty, desktopBoard))) {
  fail('canonical remote state should match the merged empty-local result')
}

const legacy = parsePinResponse({ count: 3, client_id: 'abc' })
if (legacy !== null) fail('legacy count ack must not parse as a pin snapshot')

const parsed = parsePinResponse({
  synced_at: '2026-10-23T00:00:00.000Z',
  items: [pin('Alpha', '2026-10-23T00:00:00.000Z')],
})
if (!parsed || parsed.state.items.length !== 1 || parsed.state.removed.length !== 0) fail('missing removed is an empty tombstone list')
if (parsed.syncedAt !== '2026-10-23T00:00:00.000Z') fail('synced_at should be kept')

const badItems = parsePinResponse({ items: { handle: 'nope' }, removed: [] })
if (badItems !== null) fail('non-array items must not parse')

const dropped = withDroppedHandles(
  state([pin('gone', '2026-10-20T00:00:00.000Z'), pin('stay', '2026-10-20T00:00:00.000Z')]),
  state([pin('stay', '2026-10-20T00:00:00.000Z')]),
  '2026-10-23T08:00:00.000Z',
)
if (dropped.items.length !== 1 || dropped.removed.length !== 1 || dropped.removed[0]?.handle !== 'gone') {
  fail('handles omitted from a push response become tombstones')
}
const droppedMerge = mergePins(state([pin('gone', '2026-10-20T00:00:00.000Z')]), dropped)
if (droppedMerge.items.some((item) => item.handle === 'gone')) fail('dropped launched pin must not come back')
if (!droppedMerge.removed.some((entry) => entry.handle === 'gone')) fail('dropped launched pin should stay a tombstone')

if (!isReviewedActive(mark('2026-10-20T00:00:00.000Z'))) fail('mark without cleared_at is active')
if (isReviewedActive(mark('2026-10-20T00:00:00.000Z', '2026-10-21T00:00:00.000Z'))) fail('newer cleared_at unmarks')
if (!isReviewedActive(mark('2026-10-22T00:00:00.000Z', '2026-10-21T00:00:00.000Z'))) fail('newer at restores the mark')
if (!isReviewedActive(mark('2026-10-22T00:00:00.000Z', '2026-10-22T00:00:00.000Z'))) fail('equal at and cleared_at stays marked')

const localMarks = { alpha: mark('2026-10-20T00:00:00.000Z', '', '2026-10-27T21:00:00+08:00') }
const remoteCleared = { alpha: mark('2026-10-20T00:00:00.000Z', '2026-10-23T00:00:00.000Z', '2026-10-27T21:00:00+08:00') }
const unmarked = mergeReviewed(localMarks, remoteCleared)
if (isReviewedActive(unmarked.alpha)) fail('remote clear should unmark')
if (reviewsNeedPush(localMarks, remoteCleared)) fail('older local mark must not push over a newer clear')

const nameKey = mergeReviewed(
  { 'name:foo': mark('2026-10-19T00:00:00.000Z', '', '旧') },
  { 'Name:Foo': mark('2026-10-23T00:00:00.000Z', '', '新') },
)
if (Object.keys(nameKey).join(',') !== 'name:foo') fail('review keys are lowercase')
if (nameKey['name:foo']?.snapshot.listingAt !== '新') fail('newer name: mark wins')

const phoneMarks = {}
const desktopMarks = { beta: mark('2026-10-22T00:00:00.000Z', '', '2026-10-30T00:00:00+08:00') }
const caughtUp = mergeReviewed(phoneMarks, desktopMarks)
if (!isReviewedActive(caughtUp.beta)) fail('empty phone should receive desktop 已看')
if (reviewsNeedPush(phoneMarks, desktopMarks)) fail('empty phone must not push an empty reviewed replace')

const reviewedPayload = parseReviewResponse({
  synced_at: '2026-10-23T00:00:00.000Z',
  marks: {
    Alpha: {
      at: '2026-10-23T00:00:00.000Z',
      cleared_at: '',
      snapshot: { listing_at: '2026-10-27T21:00:00+08:00', status: '即将启动', listing: '', ca: '0XABC' },
    },
  },
})
if (!reviewedPayload || !reviewedPayload.marks.alpha) fail('reviewed payload keys should be lowercase')
if (reviewedPayload.marks.alpha?.snapshot.ca !== '0xabc') fail('CA snapshot should normalize 0x')
if (reviewedPayload.marks.alpha?.snapshot.listingAt !== '2026-10-27T21:00:00+08:00') fail('listing_at should map onto listingAt')
if (parseReviewResponse({ count: 1 }) !== null) fail('legacy body must not parse as reviewed marks')

console.log('sync merge checks ok')
