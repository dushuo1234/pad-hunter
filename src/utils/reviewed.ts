/**
 * Manual 「已看」 marks. Keyed by X handle (lowercase, without @).
 * A project with no handle falls back to its normalized name.
 *
 * Stored only in localStorage (`pad-hunter.reviewed.v1`). The workbench
 * sync endpoint posts monitor pins (handle, sites, notes, push) and has
 * no reviewed field; writing marks there would pin those projects into
 * the monitor. Marks stay on this browser and survive the 20s data poll.
 */

export const REVIEWED_STORAGE_KEY = 'pad-hunter.reviewed.v1'

export interface ReviewSnapshot {
  listingAt: string
  status: string
  listing: string
  ca: string
}

export interface ReviewMark {
  at: string
  snapshot: ReviewSnapshot
}

export interface ReviewFields {
  listing_at?: string | null
  launch_at?: string | null
  status?: string | null
  listing?: string | null
  ca?: string | null
}

interface StoredMarks {
  version: 1
  marks: Record<string, ReviewMark>
}

const EMPTY_MARKS: Record<string, ReviewMark> = {}

let marks: Record<string, ReviewMark> = loadMarks()
const listeners = new Set<() => void>()

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export function reviewKey(handle?: string | null, name?: string | null): string {
  const handleKey = (handle ?? '').replace(/^@/, '').trim().toLowerCase()
  if (handleKey) return handleKey
  const nameKey = (name ?? '').trim().toLowerCase().replace(/\s+/g, ' ')
  return nameKey ? `name:${nameKey}` : ''
}

function normalizeCa(value: string): string {
  const text = value.trim()
  if (!text) return ''
  if (text.startsWith('0x') || text.startsWith('0X')) return text.toLowerCase()
  return text
}

export function reviewSnapshot(fields?: ReviewFields | null): ReviewSnapshot {
  return {
    listingAt: (fields?.listing_at || fields?.launch_at || '').trim(),
    status: (fields?.status || '').trim(),
    listing: (fields?.listing || '').trim(),
    ca: normalizeCa(fields?.ca || ''),
  }
}

function sameInstant(prev: string, next: string): boolean {
  if (prev === next) return true
  const left = Date.parse(prev)
  const right = Date.parse(next)
  if (Number.isNaN(left) || Number.isNaN(right)) return false
  return left === right
}

/** True when the live row has newer listing time, status, listing, or CA than the mark. */
export function reviewHasUpdate(stored: ReviewSnapshot, current: ReviewSnapshot): boolean {
  if (current.listingAt && !sameInstant(stored.listingAt, current.listingAt)) return true
  if (current.status && stored.status && current.status !== stored.status) return true
  if (current.listing && stored.listing && current.listing !== stored.listing) return true
  if (current.ca && current.ca !== stored.ca) return true
  return false
}

function normalizeMark(raw: unknown): ReviewMark | null {
  const row = asRecord(raw)
  if (!row) return null
  const snapshot = asRecord(row.snapshot) ?? {}
  const at = asString(row.at).trim()
  return {
    at: at || new Date(0).toISOString(),
    snapshot: {
      listingAt: asString(snapshot.listingAt).trim(),
      status: asString(snapshot.status).trim(),
      listing: asString(snapshot.listing).trim(),
      ca: normalizeCa(asString(snapshot.ca)),
    },
  }
}

function loadMarks(): Record<string, ReviewMark> {
  if (typeof localStorage === 'undefined') return EMPTY_MARKS
  try {
    const raw = localStorage.getItem(REVIEWED_STORAGE_KEY)
    if (!raw) return EMPTY_MARKS
    const parsed = asRecord(JSON.parse(raw))
    const list = asRecord(parsed?.marks)
    if (!list) return EMPTY_MARKS
    const next: Record<string, ReviewMark> = {}
    for (const [key, value] of Object.entries(list)) {
      const id = key.trim().toLowerCase()
      const mark = normalizeMark(value)
      if (!id || !mark) continue
      next[id] = mark
    }
    return Object.keys(next).length > 0 ? next : EMPTY_MARKS
  } catch {
    return EMPTY_MARKS
  }
}

export function getReviewedMarks(): Record<string, ReviewMark> {
  return marks
}

export function getReviewedServerMarks(): Record<string, ReviewMark> {
  return EMPTY_MARKS
}

export function subscribeReviewed(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange)
  const onStorage = (event: StorageEvent) => {
    if (event.key != null && event.key !== REVIEWED_STORAGE_KEY) return
    marks = loadMarks()
    onStoreChange()
  }
  if (typeof window !== 'undefined') window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(onStoreChange)
    if (typeof window !== 'undefined') window.removeEventListener('storage', onStorage)
  }
}

function commit(next: Record<string, ReviewMark>) {
  marks = next
  try {
    const payload: StoredMarks = { version: 1, marks: next }
    localStorage.setItem(REVIEWED_STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // Keep the in-memory marks if the browser refuses the write.
  }
  for (const listener of listeners) listener()
}

/** Returns the next marked state. No-op when there is no stable id. */
export function toggleReviewed(key: string, snapshot: ReviewSnapshot): boolean {
  const id = key.trim().toLowerCase()
  if (!id) return false
  if (marks[id]) {
    const next = { ...marks }
    delete next[id]
    commit(Object.keys(next).length > 0 ? next : EMPTY_MARKS)
    return false
  }
  commit({
    ...marks,
    [id]: { at: new Date().toISOString(), snapshot },
  })
  return true
}
