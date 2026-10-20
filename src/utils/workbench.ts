import type { Candidate, MonitorEvent } from '../types'
import { findByHandle } from './candidates'
import { eventsForHandle, snapshotForCandidate, summarizeEvents, type MonitorSnapshot } from './monitor'

export const WORKBENCH_STORAGE_KEY = 'pad-hunter.workbench.v1'

export interface WorkbenchItem {
  id: string
  name: string
  handle: string
  siteUrl: string
  ca: string
  caChain: string
  notes: string
  /** Sent to the monitor API as `push`. Missing stored values default on. */
  push: boolean
  pinnedAt: string
  origin: 'catalog' | 'manual'
}

export interface WorkbenchProgress {
  candidate?: Candidate
  snap: MonitorSnapshot
  eventCount: number
}

const EMPTY: WorkbenchItem[] = []

let items: WorkbenchItem[] = loadItems()
const listeners = new Set<() => void>()

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function asBool(value: unknown, fallback: boolean): boolean {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1' || value === 'true') return true
  if (value === 0 || value === '0' || value === 'false') return false
  return fallback
}

export function normalizeHandle(handle: string): string {
  return handle.replace(/^@/, '').trim()
}

export function handleKey(handle: string): string {
  return normalizeHandle(handle).toLowerCase()
}

export function safeHttpUrl(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return ''
  try {
    const url = new URL(/^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return ''
    return url.toString()
  } catch {
    return ''
  }
}

function itemId(handle: string): string {
  const key = handleKey(handle)
  if (key) return `handle:${key}`
  return `manual:${crypto.randomUUID()}`
}

function normalizeItem(raw: unknown, index: number): WorkbenchItem | null {
  const row = asRecord(raw)
  if (!row) return null
  const handle = normalizeHandle(asString(row.handle))
  const name = asString(row.name).trim().slice(0, 200)
  if (!name && !handle) return null
  const origin = row.origin === 'manual' || row.source === 'manual' ? 'manual' : 'catalog'
  const pinnedAt = asString(row.pinnedAt || row.pinned_at).trim()
  return {
    id: asString(row.id).trim().slice(0, 80) || itemId(handle) || `manual:import-${index}`,
    name: name || handle,
    handle,
    siteUrl: safeHttpUrl(asString(row.siteUrl || row.site_url || row.site)),
    ca: asString(row.ca).trim().slice(0, 200),
    caChain: asString(row.caChain || row.ca_chain || row.chain).trim().slice(0, 80),
    notes: asString(row.notes).slice(0, 20_000),
    push: asBool(row.push, true),
    pinnedAt: pinnedAt || new Date().toISOString(),
    origin,
  }
}

export function parseWorkbenchItems(data: unknown): WorkbenchItem[] {
  const list = Array.isArray(data)
    ? data
    : Array.isArray(asRecord(data)?.items)
      ? (asRecord(data)?.items as unknown[])
      : null
  if (!list) throw new Error('JSON 需包含 items 数组')
  const parsed: WorkbenchItem[] = []
  const seenHandles = new Set<string>()
  const seenIds = new Set<string>()
  for (const [index, raw] of list.entries()) {
    const item = normalizeItem(raw, index)
    if (!item) continue
    const key = handleKey(item.handle)
    if (key) {
      if (seenHandles.has(key)) continue
      seenHandles.add(key)
    }
    if (seenIds.has(item.id)) item.id = `${item.id}-${index}`
    seenIds.add(item.id)
    parsed.push(item)
  }
  return parsed
}

function loadItems(): WorkbenchItem[] {
  if (typeof localStorage === 'undefined') return EMPTY
  try {
    const raw = localStorage.getItem(WORKBENCH_STORAGE_KEY)
    if (!raw) return EMPTY
    const parsed = parseWorkbenchItems(JSON.parse(raw))
    return parsed.length > 0 ? parsed : EMPTY
  } catch {
    return EMPTY
  }
}

export function getWorkbenchItems(): WorkbenchItem[] {
  return items
}

export function subscribeWorkbench(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange)
  const onStorage = (event: StorageEvent) => {
    if (event.key != null && event.key !== WORKBENCH_STORAGE_KEY) return
    items = loadItems()
    onStoreChange()
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(onStoreChange)
    window.removeEventListener('storage', onStorage)
  }
}

function commit(next: WorkbenchItem[]) {
  items = next
  try {
    localStorage.setItem(WORKBENCH_STORAGE_KEY, JSON.stringify({ version: 1, items: next }))
  } catch {
    // Keep the in-memory board if the browser refuses the write.
  }
  for (const listener of listeners) listener()
}

function indexByHandle(list: WorkbenchItem[], handle: string): number {
  const key = handleKey(handle)
  if (!key) return -1
  return list.findIndex((item) => handleKey(item.handle) === key)
}

export function isHandlePinned(list: WorkbenchItem[], handle: string): boolean {
  return indexByHandle(list, handle) >= 0
}

export type PinResult = 'added' | 'updated'

export function pinCandidate(candidate: Candidate): PinResult {
  const handle = normalizeHandle(candidate.handle)
  const list = items.slice()
  const index = indexByHandle(list, handle)
  const extraSite = (candidate as Candidate & { site?: string }).site
  const site = candidate.sites?.map((url) => safeHttpUrl(url)).find(Boolean) || safeHttpUrl(extraSite || '') || ''
  const ca = candidate.ca?.trim() ?? ''
  const caChain = (candidate.ca_chain || '').trim()
  if (index >= 0) {
    const prev = list[index]
    list[index] = {
      ...prev,
      name: candidate.name.trim() || prev.name,
      handle: handle || prev.handle,
      siteUrl: prev.siteUrl || site,
      ca: prev.ca || ca,
      caChain: prev.caChain || caChain,
    }
    commit(list)
    return 'updated'
  }
  list.unshift({
    id: itemId(handle),
    name: candidate.name.trim() || handle || '未命名项目',
    handle,
    siteUrl: site,
    ca,
    caChain,
    notes: '',
    push: true,
    pinnedAt: new Date().toISOString(),
    origin: 'catalog',
  })
  commit(list)
  return 'added'
}

export interface ManualPinInput {
  name: string
  handle: string
  siteUrl: string
  ca: string
  caChain: string
  origin?: WorkbenchItem['origin']
}

export function pinManual(input: ManualPinInput): PinResult {
  const handle = normalizeHandle(input.handle)
  const name = input.name.trim().slice(0, 200)
  if (!name && !handle) throw new Error('请填写名称或 X 账号')
  const list = items.slice()
  const siteUrl = safeHttpUrl(input.siteUrl)
  const ca = input.ca.trim().slice(0, 200)
  const caChain = input.caChain.trim().slice(0, 80)
  const index = indexByHandle(list, handle)
  if (index >= 0) {
    const prev = list[index]
    list[index] = {
      ...prev,
      name: name || prev.name,
      handle,
      siteUrl: siteUrl || prev.siteUrl,
      ca: ca || prev.ca,
      caChain: caChain || prev.caChain,
    }
    commit(list)
    return 'updated'
  }
  list.unshift({
    id: itemId(handle),
    name: name || handle,
    handle,
    siteUrl,
    ca,
    caChain,
    notes: '',
    push: true,
    pinnedAt: new Date().toISOString(),
    origin: input.origin ?? 'manual',
  })
  commit(list)
  return 'added'
}

export function pinObserved(input: { name: string; handle: string; candidate?: Candidate | null }): PinResult {
  if (input.candidate) return pinCandidate(input.candidate)
  return pinManual({
    name: input.name,
    handle: input.handle,
    siteUrl: '',
    ca: '',
    caChain: '',
    origin: 'catalog',
  })
}

export function updateWorkbenchNotes(id: string, notes: string): void {
  const index = items.findIndex((item) => item.id === id)
  if (index < 0 || items[index].notes === notes) return
  const next = items.slice()
  next[index] = { ...next[index], notes: notes.slice(0, 20_000) }
  commit(next)
}

export function setWorkbenchPush(id: string, push: boolean): void {
  const index = items.findIndex((item) => item.id === id)
  if (index < 0 || items[index].push === push) return
  const next = items.slice()
  next[index] = { ...next[index], push }
  commit(next)
}

export function removeWorkbenchItem(id: string): void {
  commit(items.filter((item) => item.id !== id))
}

export function removeWorkbenchItems(ids: Iterable<string>): void {
  const drop = new Set(ids)
  if (drop.size === 0) return
  commit(items.filter((item) => !drop.has(item.id)))
}

export function replaceWorkbench(next: WorkbenchItem[]): void {
  commit(next)
}

export function progressForItem(item: WorkbenchItem, candidates: Candidate[], events: MonitorEvent[]): WorkbenchProgress {
  const candidate = item.handle ? findByHandle(candidates, item.handle) : undefined
  const matched = item.handle ? eventsForHandle(events, item.handle) : []
  const snap = candidate ? snapshotForCandidate(candidate, events) : summarizeEvents(matched)
  if (!snap.ca && item.ca) {
    snap.ca = item.ca
    snap.caChain = item.caChain || snap.caChain
  }
  return { candidate, snap, eventCount: matched.length }
}

export function searchCatalog(candidates: Candidate[], query: string): Candidate[] {
  const q = query.trim().toLowerCase().replace(/^@/, '')
  if (!q) return []
  const sorted = [...candidates].sort(
    (a, b) => (Date.parse(b.date_iso || '') || 0) - (Date.parse(a.date_iso || '') || 0),
  )
  const seen = new Set<string>()
  const matches: Candidate[] = []
  for (const candidate of sorted) {
    const key = handleKey(candidate.handle)
    if (key && seen.has(key)) continue
    const hay = `${candidate.name} ${candidate.handle}`.toLowerCase()
    if (!hay.includes(q)) continue
    if (key) seen.add(key)
    matches.push(candidate)
    if (matches.length >= 8) break
  }
  return matches
}
