/**
 * Manual 「已看」 marks. Keyed by X handle (lowercase, without @).
 * A project with no handle falls back to its normalized name (`name:…`).
 *
 * localStorage (`pad-hunter.reviewed.v1`) is the offline cache. With a token,
 * marks also merge through `/v1/workbench/reviewed`. Turning a mark off writes
 * `clearedAt` instead of deleting the key, so another device can learn the unmark.
 * A key is shown as reviewed only while `at` is newer than or equal to `clearedAt`.
 */

import { isReviewedActive, nowIso } from './syncMerge'

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
  /** Set when the mark was turned off. Newer than `at` means unmarked. */
  clearedAt?: string
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

let stored: Record<string, ReviewMark> = EMPTY_MARKS
let active: Record<string, ReviewMark> = EMPTY_MARKS
const listeners = new Set<() => void>()
let silentReviewed = 0

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
export function reviewHasUpdate(storedSnapshot: ReviewSnapshot, current: ReviewSnapshot): boolean {
  if (current.listingAt && !sameInstant(storedSnapshot.listingAt, current.listingAt)) return true
  if (current.status && storedSnapshot.status && current.status !== storedSnapshot.status) return true
  if (current.listing && storedSnapshot.listing && current.listing !== storedSnapshot.listing) return true
  if (current.ca && current.ca !== storedSnapshot.ca) return true
  return false
}

function markIsActive(mark: ReviewMark): boolean {
  return isReviewedActive({ at: mark.at, clearedAt: mark.clearedAt })
}

function projectActive(all: Record<string, ReviewMark>): Record<string, ReviewMark> {
  const next: Record<string, ReviewMark> = {}
  for (const [key, mark] of Object.entries(all)) {
    if (markIsActive(mark)) next[key] = mark
  }
  return Object.keys(next).length > 0 ? next : EMPTY_MARKS
}

function normalizeMark(raw: unknown): ReviewMark | null {
  const row = asRecord(raw)
  if (!row) return null
  const snapshot = asRecord(row.snapshot) ?? {}
  const at = asString(row.at).trim()
  const clearedAt = asString(row.clearedAt || row.cleared_at).trim()
  if (!at && !clearedAt) return null
  return {
    at: at || new Date(0).toISOString(),
    snapshot: {
      listingAt: asString(snapshot.listingAt || snapshot.listing_at).trim(),
      status: asString(snapshot.status).trim(),
      listing: asString(snapshot.listing).trim(),
      ca: normalizeCa(asString(snapshot.ca)),
    },
    ...(clearedAt ? { clearedAt } : {}),
  }
}

function loadStored(): Record<string, ReviewMark> {
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

stored = loadStored()
active = projectActive(stored)

/** Active marks only. Cleared keys are absent so existing 「已看」 checks keep working. */
export function getReviewedMarks(): Record<string, ReviewMark> {
  return active
}

/** Full cache, including tombstones, for the sync client. */
export function getReviewedSyncMarks(): Record<string, ReviewMark> {
  return stored
}

export function getReviewedServerMarks(): Record<string, ReviewMark> {
  return EMPTY_MARKS
}

export function isReviewedWriteSuppressed(): boolean {
  return silentReviewed > 0
}

export function subscribeReviewed(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange)
  const onStorage = (event: StorageEvent) => {
    if (event.key != null && event.key !== REVIEWED_STORAGE_KEY) return
    stored = loadStored()
    active = projectActive(stored)
    onStoreChange()
  }
  if (typeof window !== 'undefined') window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(onStoreChange)
    if (typeof window !== 'undefined') window.removeEventListener('storage', onStorage)
  }
}

function sameStored(left: Record<string, ReviewMark>, right: Record<string, ReviewMark>): boolean {
  const leftKeys = Object.keys(left)
  const rightKeys = Object.keys(right)
  if (leftKeys.length !== rightKeys.length) return false
  for (const key of leftKeys) {
    const a = left[key]
    const b = right[key]
    if (!a || !b) return false
    if (a.at !== b.at || (a.clearedAt ?? '') !== (b.clearedAt ?? '')) return false
    if (
      a.snapshot.listingAt !== b.snapshot.listingAt ||
      a.snapshot.status !== b.snapshot.status ||
      a.snapshot.listing !== b.snapshot.listing ||
      a.snapshot.ca !== b.snapshot.ca
    ) {
      return false
    }
  }
  return true
}

function publish(next: Record<string, ReviewMark>) {
  const normalized = Object.keys(next).length > 0 ? next : EMPTY_MARKS
  if (sameStored(stored, normalized)) return
  stored = normalized
  active = projectActive(stored)
  try {
    const payload: StoredMarks = { version: 1, marks: stored }
    localStorage.setItem(REVIEWED_STORAGE_KEY, JSON.stringify(payload))
  } catch {
    // Keep the in-memory marks if the browser refuses the write.
  }
  for (const listener of listeners) listener()
}

/** Replace the cache from a merged sync snapshot without scheduling another push. */
export function replaceReviewedMarks(next: Record<string, ReviewMark>): void {
  silentReviewed += 1
  try {
    publish(next)
  } finally {
    silentReviewed -= 1
  }
}

/** Returns the next marked state. No-op when there is no stable id. */
export function toggleReviewed(key: string, snapshot: ReviewSnapshot): boolean {
  const id = key.trim().toLowerCase()
  if (!id) return false
  const current = stored[id]
  if (current && markIsActive(current)) {
    publish({
      ...stored,
      [id]: { ...current, clearedAt: nowIso() },
    })
    return false
  }
  publish({
    ...stored,
    [id]: {
      at: nowIso(),
      snapshot,
      ...(current?.clearedAt ? { clearedAt: current.clearedAt } : {}),
    },
  })
  return true
}
