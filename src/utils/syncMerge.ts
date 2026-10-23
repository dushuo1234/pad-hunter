/**
 * Pure last-write-wins merge for workbench pins and 「已看」 marks.
 * Pins compete per lowercase handle: a tombstone wins only when removed_at
 * is strictly newer than updated_at. Reviewed marks compete per key on
 * max(at, cleared_at); cleared_at newer than at means unmarked.
 * Equal timestamps keep the remote side so two devices converge after a pull.
 */

export interface PinWire {
  handle: string
  name: string
  sites: string[]
  x_url: string
  chain: string
  notes: string
  push: boolean
  added_at: string
  updated_at: string
}

export interface PinRemovalWire {
  handle: string
  removed_at: string
}

export interface PinMergeState {
  items: PinWire[]
  removed: PinRemovalWire[]
}

export interface ReviewSnapshotWire {
  listingAt: string
  status: string
  listing: string
  ca: string
}

export interface ReviewWire {
  at: string
  snapshot: ReviewSnapshotWire
  cleared_at: string
}

export interface PinResponse {
  syncedAt: string
  state: PinMergeState
}

export interface ReviewResponse {
  syncedAt: string
  marks: Record<string, ReviewWire>
}

const EMPTY_PINS: PinMergeState = { items: [], removed: [] }

export function pinHandleKey(handle: string): string {
  return handle.replace(/^@/, '').trim().toLowerCase()
}

export function timestampMs(value: string | null | undefined): number {
  if (!value) return 0
  const ms = Date.parse(value)
  return Number.isFinite(ms) ? ms : 0
}

export function nowIso(): string {
  return new Date().toISOString()
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function asBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1' || value === 'true') return true
  if (value === 0 || value === '0' || value === 'false') return false
  return fallback
}

function laterPin(local: PinWire | undefined, remote: PinWire | undefined): PinWire | undefined {
  if (!local) return remote
  if (!remote) return local
  const left = timestampMs(local.updated_at)
  const right = timestampMs(remote.updated_at)
  if (right > left) return remote
  if (left > right) return local
  return remote
}

function laterRemoval(local: PinRemovalWire | undefined, remote: PinRemovalWire | undefined): PinRemovalWire | undefined {
  if (!local) return remote
  if (!remote) return local
  const left = timestampMs(local.removed_at)
  const right = timestampMs(remote.removed_at)
  if (right > left) return remote
  if (left > right) return local
  return remote
}

function indexPins(items: PinWire[]): Map<string, PinWire> {
  const map = new Map<string, PinWire>()
  for (const item of items) {
    const key = pinHandleKey(item.handle)
    if (!key) continue
    const prev = map.get(key)
    if (!prev || timestampMs(item.updated_at) >= timestampMs(prev.updated_at)) map.set(key, item)
  }
  return map
}

function indexRemovals(removed: PinRemovalWire[]): Map<string, PinRemovalWire> {
  const map = new Map<string, PinRemovalWire>()
  for (const entry of removed) {
    const key = pinHandleKey(entry.handle)
    if (!key) continue
    const prev = map.get(key)
    if (!prev || timestampMs(entry.removed_at) >= timestampMs(prev.removed_at)) map.set(key, entry)
  }
  return map
}

export function mergePins(local: PinMergeState, remote: PinMergeState): PinMergeState {
  const localItems = indexPins(local.items)
  const remoteItems = indexPins(remote.items)
  const localRemoved = indexRemovals(local.removed)
  const remoteRemoved = indexRemovals(remote.removed)
  const keys = new Set<string>([...localItems.keys(), ...remoteItems.keys(), ...localRemoved.keys(), ...remoteRemoved.keys()])

  const items: PinWire[] = []
  const removed: PinRemovalWire[] = []
  for (const key of keys) {
    const item = laterPin(localItems.get(key), remoteItems.get(key))
    const tomb = laterRemoval(localRemoved.get(key), remoteRemoved.get(key))
    const itemAt = item ? timestampMs(item.updated_at) : 0
    const tombAt = tomb ? timestampMs(tomb.removed_at) : 0
    if (tomb && tombAt > itemAt) {
      removed.push({ handle: pinHandleKey(tomb.handle) || key, removed_at: tomb.removed_at })
      continue
    }
    if (item && pinHandleKey(item.handle)) {
      items.push(item)
    }
  }
  items.sort((a, b) => pinHandleKey(a.handle).localeCompare(pinHandleKey(b.handle)))
  removed.sort((a, b) => pinHandleKey(a.handle).localeCompare(pinHandleKey(b.handle)))
  return { items, removed }
}

function canonPin(item: PinWire) {
  return {
    handle: pinHandleKey(item.handle),
    name: item.name,
    sites: item.sites,
    x_url: item.x_url,
    chain: item.chain,
    notes: item.notes,
    push: Boolean(item.push),
    added_at: item.added_at,
    updated_at: item.updated_at,
  }
}

export function canonicalPinState(state: PinMergeState): string {
  const merged = mergePins(EMPTY_PINS, state)
  return JSON.stringify({
    items: merged.items.map(canonPin),
    removed: merged.removed.map((entry) => ({
      handle: pinHandleKey(entry.handle),
      removed_at: entry.removed_at,
    })),
  })
}

/** True when merging `local` into `remote` would change the server snapshot. */
export function pinsNeedPush(local: PinMergeState, remote: PinMergeState): boolean {
  const merged = mergePins(local, remote)
  const remoteNorm = mergePins(EMPTY_PINS, remote)
  return canonicalPinState(merged) !== canonicalPinState(remoteNorm)
}

export function isReviewedActive(mark: { at?: string | null; cleared_at?: string | null; clearedAt?: string | null }): boolean {
  const at = timestampMs(mark.at)
  const cleared = timestampMs(mark.cleared_at || mark.clearedAt)
  return at > 0 && cleared <= at
}

export function reviewRevisionMs(mark: { at?: string | null; cleared_at?: string | null; clearedAt?: string | null }): number {
  return Math.max(timestampMs(mark.at), timestampMs(mark.cleared_at || mark.clearedAt))
}

function pickReview(local: ReviewWire | undefined, remote: ReviewWire | undefined): ReviewWire | undefined {
  if (!local) return remote
  if (!remote) return local
  const left = reviewRevisionMs(local)
  const right = reviewRevisionMs(remote)
  if (right > left) return remote
  if (left > right) return local
  return remote
}

function indexReviews(marks: Record<string, ReviewWire>): Map<string, ReviewWire> {
  const map = new Map<string, ReviewWire>()
  for (const [key, mark] of Object.entries(marks)) {
    const id = key.trim().toLowerCase()
    if (!id || !mark) continue
    const prev = map.get(id)
    map.set(id, prev && reviewRevisionMs(prev) > reviewRevisionMs(mark) ? prev : mark)
  }
  return map
}

export function mergeReviewed(local: Record<string, ReviewWire>, remote: Record<string, ReviewWire>): Record<string, ReviewWire> {
  const localMarks = indexReviews(local)
  const remoteMarks = indexReviews(remote)
  const keys = new Set<string>([...localMarks.keys(), ...remoteMarks.keys()])
  const marks: Record<string, ReviewWire> = {}
  for (const key of keys) {
    const winner = pickReview(localMarks.get(key), remoteMarks.get(key))
    if (!winner) continue
    if (!winner.at && !winner.cleared_at) continue
    marks[key] = winner
  }
  return marks
}

function canonReview(mark: ReviewWire) {
  return {
    at: mark.at,
    cleared_at: mark.cleared_at,
    snapshot: {
      listingAt: mark.snapshot.listingAt,
      status: mark.snapshot.status,
      listing: mark.snapshot.listing,
      ca: mark.snapshot.ca,
    },
  }
}

export function canonicalReviewState(marks: Record<string, ReviewWire>): string {
  const merged = mergeReviewed({}, marks)
  const keys = Object.keys(merged).sort()
  return JSON.stringify(keys.map((key) => [key, canonReview(merged[key])]))
}

export function reviewsNeedPush(local: Record<string, ReviewWire>, remote: Record<string, ReviewWire>): boolean {
  return canonicalReviewState(mergeReviewed(local, remote)) !== canonicalReviewState(mergeReviewed({}, remote))
}

function parseSites(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : []
  const sites: string[] = []
  const seen = new Set<string>()
  for (const entry of raw) {
    const site = typeof entry === 'string' ? entry.trim() : ''
    if (!site || seen.has(site)) continue
    seen.add(site)
    sites.push(site)
  }
  return sites
}

function parsePinItem(raw: unknown): PinWire | null {
  const row = asRecord(raw)
  if (!row) return null
  const handle = asString(row.handle).replace(/^@/, '')
  if (!pinHandleKey(handle)) return null
  const notes = typeof row.notes === 'string' ? row.notes.slice(0, 20_000) : ''
  return {
    handle,
    name: asString(row.name).slice(0, 200) || handle,
    sites: parseSites(row.sites),
    x_url: asString(row.x_url || row.xUrl),
    chain: asString(row.chain).slice(0, 80),
    notes,
    push: asBool(row.push, true),
    added_at: asString(row.added_at || row.addedAt),
    updated_at: asString(row.updated_at || row.updatedAt),
  }
}

function parseRemoval(raw: unknown): PinRemovalWire | null {
  const row = asRecord(raw)
  if (!row) return null
  const handle = asString(row.handle).replace(/^@/, '')
  const removedAt = asString(row.removed_at || row.removedAt)
  if (!pinHandleKey(handle) || !removedAt) return null
  return { handle, removed_at: removedAt }
}

/** New pin document. `{ count }` and other legacy sync acks return null. */
export function parsePinResponse(data: unknown): PinResponse | null {
  const row = asRecord(data)
  if (!row) return null
  if (!('items' in row) && !('removed' in row)) return null
  if ('items' in row && !Array.isArray(row.items)) return null
  if ('removed' in row && row.removed != null && !Array.isArray(row.removed)) return null
  const items: PinWire[] = []
  for (const entry of Array.isArray(row.items) ? row.items : []) {
    const item = parsePinItem(entry)
    if (item) items.push(item)
  }
  const removed: PinRemovalWire[] = []
  for (const entry of Array.isArray(row.removed) ? row.removed : []) {
    const tomb = parseRemoval(entry)
    if (tomb) removed.push(tomb)
  }
  return {
    syncedAt: asString(row.synced_at || row.syncedAt),
    state: { items, removed },
  }
}

function parseSnapshot(value: unknown): ReviewSnapshotWire {
  const row = asRecord(value) ?? {}
  const caRaw = typeof row.ca === 'string' ? row.ca.trim() : ''
  const ca = caRaw.startsWith('0x') || caRaw.startsWith('0X') ? caRaw.toLowerCase() : caRaw
  return {
    listingAt: asString(row.listingAt || row.listing_at),
    status: asString(row.status),
    listing: asString(row.listing),
    ca,
  }
}

function parseReviewMark(raw: unknown): ReviewWire | null {
  const row = asRecord(raw)
  if (!row) return null
  const at = asString(row.at)
  const cleared = asString(row.cleared_at || row.clearedAt)
  if (!at && !cleared) return null
  return { at, snapshot: parseSnapshot(row.snapshot), cleared_at: cleared }
}

export function parseReviewResponse(data: unknown): ReviewResponse | null {
  const row = asRecord(data)
  if (!row || !('marks' in row)) return null
  if (row.marks == null) {
    return { syncedAt: asString(row.synced_at || row.syncedAt), marks: {} }
  }
  const marksRow = asRecord(row.marks)
  if (!marksRow) return null
  const marks: Record<string, ReviewWire> = {}
  for (const [key, value] of Object.entries(marksRow)) {
    const id = key.trim().toLowerCase()
    const mark = parseReviewMark(value)
    if (!id || !mark) continue
    const prev = marks[id]
    marks[id] = prev && reviewRevisionMs(prev) > reviewRevisionMs(mark) ? prev : mark
  }
  return { syncedAt: asString(row.synced_at || row.syncedAt), marks }
}

/**
 * Handles we sent that the merged response dropped entirely were removed server-side
 * (launched projects). Record a tombstone so the next merge does not resurrect them.
 */
export function withDroppedHandles(sent: PinMergeState, response: PinMergeState, removedAt: string): PinMergeState {
  const present = new Set<string>()
  for (const item of response.items) {
    const key = pinHandleKey(item.handle)
    if (key) present.add(key)
  }
  for (const tomb of response.removed) {
    const key = pinHandleKey(tomb.handle)
    if (key) present.add(key)
  }
  const removed = response.removed.slice()
  for (const item of sent.items) {
    const key = pinHandleKey(item.handle)
    if (!key || present.has(key)) continue
    removed.push({ handle: key, removed_at: removedAt })
    present.add(key)
  }
  return { items: response.items.slice(), removed }
}
