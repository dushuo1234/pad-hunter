import type { Candidate, MonitorEvent } from '../types'
import { findByHandle } from './candidates'
import { eventsForHandle, snapshotForCandidate, summarizeEvents, type MonitorSnapshot } from './monitor'
import { nowIso, timestampMs, type PinWire } from './syncMerge'

export const WORKBENCH_STORAGE_KEY = 'pad-hunter.workbench.v1'

export interface WorkbenchTombstone {
  handle: string
  removedAt: string
}

export interface WorkbenchItem {
  id: string
  name: string
  handle: string
  siteUrl: string
  /** Synced site list. Empty until a server round-trip or an explicit edit. */
  sites: string[]
  /** True once `sites` is the list we should send, not a catalog derivation. */
  sitesSynced: boolean
  xUrl: string
  /** Project chain last agreed with the monitor. Distinct from the CA chain. */
  chain: string
  ca: string
  caChain: string
  notes: string
  /** Sent to the monitor API as `push`. Missing stored values default on. */
  push: boolean
  pinnedAt: string
  updatedAt: string
  origin: 'catalog' | 'manual'
}

export interface WorkbenchProgress {
  candidate?: Candidate
  snap: MonitorSnapshot
  eventCount: number
}

const EMPTY: WorkbenchItem[] = []
const EMPTY_TOMBS: WorkbenchTombstone[] = []

const loadedBoard = loadState()
let items: WorkbenchItem[] = loadedBoard.items
let tombstones: WorkbenchTombstone[] = loadedBoard.tombstones
const listeners = new Set<() => void>()
let silentPins = 0
let autoRemoveMessage: string | null = null
const autoRemoveListeners = new Set<() => void>()
let autoRemoveSubscribers = 0
let autoRemoveIdleTimer = 0

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

function parseSites(value: unknown): string[] | null {
  if (!Array.isArray(value)) return null
  const sites: string[] = []
  const seen = new Set<string>()
  for (const entry of value) {
    const url = safeHttpUrl(asString(entry))
    if (!url || seen.has(url)) continue
    seen.add(url)
    sites.push(url)
  }
  return sites
}

function normalizeItem(raw: unknown, index: number): WorkbenchItem | null {
  const row = asRecord(raw)
  if (!row) return null
  const handle = normalizeHandle(asString(row.handle))
  const name = asString(row.name).trim().slice(0, 200)
  if (!name && !handle) return null
  const origin = row.origin === 'manual' || row.source === 'manual' ? 'manual' : 'catalog'
  const pinnedAt = asString(row.pinnedAt || row.pinned_at).trim()
  const updatedAt = asString(row.updatedAt || row.updated_at).trim()
  const hasExplicitCa = 'caChain' in row || 'ca_chain' in row
  const explicitCa = asString(row.caChain || row.ca_chain).trim()
  const chainField = asString(row.chain).trim().slice(0, 80)
  const siteUrl = safeHttpUrl(asString(row.siteUrl || row.site_url || row.site))
  const sites = parseSites(row.sites)
  const storedAt = pinnedAt || updatedAt || new Date().toISOString()
  return {
    id: asString(row.id).trim().slice(0, 80) || itemId(handle) || `manual:import-${index}`,
    name: name || handle,
    handle,
    siteUrl: siteUrl || sites?.[0] || '',
    sites: sites ?? (siteUrl ? [siteUrl] : []),
    sitesSynced: row.sitesSynced === true || Array.isArray(row.sites),
    xUrl: safeHttpUrl(asString(row.xUrl || row.x_url)),
    chain: (hasExplicitCa ? chainField : '').slice(0, 80),
    ca: asString(row.ca).trim().slice(0, 200),
    caChain: (hasExplicitCa ? explicitCa : chainField).slice(0, 80),
    notes: typeof row.notes === 'string' ? row.notes.slice(0, 20_000) : '',
    push: asBool(row.push, true),
    pinnedAt: storedAt,
    updatedAt: updatedAt || storedAt,
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

function parseTombstones(value: unknown): WorkbenchTombstone[] {
  if (!Array.isArray(value)) return []
  const out: WorkbenchTombstone[] = []
  const seen = new Set<string>()
  for (const entry of value) {
    const row = asRecord(entry)
    if (!row) continue
    const handle = handleKey(asString(row.handle))
    const removedAt = asString(row.removedAt || row.removed_at)
    if (!handle || !removedAt || seen.has(handle)) continue
    seen.add(handle)
    out.push({ handle, removedAt })
  }
  return out
}

function winningTombstones(list: WorkbenchItem[], removed: WorkbenchTombstone[]): WorkbenchTombstone[] {
  const itemAt = new Map<string, number>()
  for (const item of list) {
    const key = handleKey(item.handle)
    if (!key) continue
    itemAt.set(key, Math.max(itemAt.get(key) ?? 0, timestampMs(item.updatedAt || item.pinnedAt)))
  }
  return removed.filter((entry) => timestampMs(entry.removedAt) > (itemAt.get(entry.handle) ?? 0))
}

function visibleItems(list: WorkbenchItem[], removed: WorkbenchTombstone[]): WorkbenchItem[] {
  const tombAt = new Map(removed.map((entry) => [entry.handle, timestampMs(entry.removedAt)]))
  return list.filter((item) => {
    const key = handleKey(item.handle)
    if (!key) return true
    return (tombAt.get(key) ?? 0) <= timestampMs(item.updatedAt || item.pinnedAt)
  })
}

function loadState(): { items: WorkbenchItem[]; tombstones: WorkbenchTombstone[] } {
  if (typeof localStorage === 'undefined') return { items: EMPTY, tombstones: EMPTY_TOMBS }
  try {
    const raw = localStorage.getItem(WORKBENCH_STORAGE_KEY)
    if (!raw) return { items: EMPTY, tombstones: EMPTY_TOMBS }
    const parsed = JSON.parse(raw) as unknown
    const loaded = parseWorkbenchItems(parsed)
    const removed = parseTombstones(asRecord(parsed)?.removed)
    const tombs = winningTombstones(loaded, removed)
    const visible = visibleItems(loaded, tombs)
    return {
      items: visible.length > 0 ? visible : EMPTY,
      tombstones: tombs.length > 0 ? tombs : EMPTY_TOMBS,
    }
  } catch {
    return { items: EMPTY, tombstones: EMPTY_TOMBS }
  }
}

export function getWorkbenchItems(): WorkbenchItem[] {
  return items
}

export function subscribeWorkbench(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange)
  const onStorage = (event: StorageEvent) => {
    if (event.key != null && event.key !== WORKBENCH_STORAGE_KEY) return
    ;({ items, tombstones } = loadState())
    onStoreChange()
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(onStoreChange)
    window.removeEventListener('storage', onStorage)
  }
}

export function getAutoRemoveMessage(): string | null {
  return autoRemoveMessage
}

export function subscribeAutoRemoveMessage(onStoreChange: () => void): () => void {
  autoRemoveListeners.add(onStoreChange)
  autoRemoveSubscribers += 1
  if (typeof window !== 'undefined') window.clearTimeout(autoRemoveIdleTimer)
  return () => {
    autoRemoveListeners.delete(onStoreChange)
    autoRemoveSubscribers -= 1
    if (autoRemoveSubscribers > 0 || typeof window === 'undefined') return
    autoRemoveIdleTimer = window.setTimeout(() => {
      if (autoRemoveSubscribers > 0 || autoRemoveMessage == null) return
      autoRemoveMessage = null
    }, 0)
  }
}

function announceAutoRemove(count: number) {
  if (count <= 0) return
  const previous = Number(/^已自动移出已开盘 (\d+) 个$/.exec(autoRemoveMessage ?? '')?.[1] ?? 0)
  autoRemoveMessage = `已自动移出已开盘 ${previous + count} 个`
  for (const listener of autoRemoveListeners) listener()
}

function commit(next: WorkbenchItem[], nextRemoved?: WorkbenchTombstone[]) {
  const removed = winningTombstones(next, nextRemoved ?? tombstones)
  const visible = visibleItems(next, removed)
  items = visible.length > 0 ? visible : EMPTY
  tombstones = removed.length > 0 ? removed : EMPTY_TOMBS
  try {
    localStorage.setItem(
      WORKBENCH_STORAGE_KEY,
      JSON.stringify({ version: 2, items, removed: tombstones }),
    )
  } catch {
    // Keep the in-memory board if the browser refuses the write.
  }
  for (const listener of listeners) listener()
}

export function getWorkbenchTombstones(): WorkbenchTombstone[] {
  return tombstones
}

export function isPinApplySilent(): boolean {
  return silentPins > 0
}

function boardSignature(list: WorkbenchItem[], removed: WorkbenchTombstone[]): string {
  return JSON.stringify({
    items: list.map((item) => [
      item.id,
      item.handle,
      item.name,
      item.siteUrl,
      item.sites,
      item.sitesSynced,
      item.xUrl,
      item.chain,
      item.ca,
      item.caChain,
      item.notes,
      item.push,
      item.pinnedAt,
      item.updatedAt,
      item.origin,
    ]),
    removed: removed.map((entry) => [entry.handle, entry.removedAt]),
  })
}

/** Replace the board from a merged sync snapshot without scheduling another push. */
export function applyIntegratedPins(next: WorkbenchItem[], removed: WorkbenchTombstone[]): void {
  const removedNorm = winningTombstones(next, removed)
  const visible = visibleItems(next, removedNorm)
  const nextItems = visible.length > 0 ? visible : EMPTY
  const nextTombs = removedNorm.length > 0 ? removedNorm : EMPTY_TOMBS
  if (boardSignature(nextItems, nextTombs) === boardSignature(items, tombstones)) return
  silentPins += 1
  try {
    commit(nextItems, nextTombs)
  } finally {
    silentPins -= 1
  }
}

export function workbenchItemFromWire(wire: PinWire, prev?: WorkbenchItem): WorkbenchItem {
  const handle = normalizeHandle(wire.handle)
  const sites: string[] = []
  const seen = new Set<string>()
  for (const entry of wire.sites) {
    const url = safeHttpUrl(entry)
    if (!url || seen.has(url)) continue
    seen.add(url)
    sites.push(url)
  }
  const pinnedAt = wire.added_at.trim() || prev?.pinnedAt || wire.updated_at.trim() || nowIso()
  return {
    id: prev?.id || itemId(handle),
    name: wire.name.trim().slice(0, 200) || prev?.name || handle,
    handle: handle || prev?.handle || '',
    siteUrl: sites[0] || '',
    sites,
    sitesSynced: true,
    xUrl: safeHttpUrl(wire.x_url),
    chain: wire.chain.trim().slice(0, 80),
    ca: prev?.ca ?? '',
    caChain: prev?.caChain ?? '',
    notes: wire.notes.slice(0, 20_000),
    push: wire.push,
    pinnedAt,
    updatedAt: wire.updated_at.trim() || prev?.updatedAt || pinnedAt,
    origin: prev?.origin ?? 'manual',
  }
}

function clearTombstone(handle: string): WorkbenchTombstone[] {
  const key = handleKey(handle)
  if (!key) return tombstones
  return tombstones.filter((entry) => entry.handle !== key)
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
    const name = candidate.name.trim() || prev.name
    const nextHandle = handle || prev.handle
    const siteUrl = prev.siteUrl || site
    const nextCa = prev.ca || ca
    const nextCaChain = prev.caChain || caChain
    const syncedChanged = name !== prev.name || nextHandle !== prev.handle || siteUrl !== prev.siteUrl
    const localChanged = nextCa !== prev.ca || nextCaChain !== prev.caChain
    const tomb = tombstones.find((entry) => entry.handle === handleKey(nextHandle))
    const reaffirm = Boolean(tomb && timestampMs(tomb.removedAt) > timestampMs(prev.updatedAt || prev.pinnedAt))
    if (!syncedChanged && !localChanged && !reaffirm) return 'updated'
    const sites =
      siteUrl && siteUrl !== prev.siteUrl ? [siteUrl, ...prev.sites.filter((url) => url !== siteUrl)] : prev.sites
    list[index] = {
      ...prev,
      name,
      handle: nextHandle,
      siteUrl,
      sites,
      sitesSynced: siteUrl !== prev.siteUrl ? false : prev.sitesSynced,
      ca: nextCa,
      caChain: nextCaChain,
      updatedAt: syncedChanged || reaffirm ? nowIso() : prev.updatedAt,
    }
    commit(list, syncedChanged || reaffirm ? clearTombstone(nextHandle) : tombstones)
    return 'updated'
  }
  const pinnedAt = nowIso()
  list.unshift({
    id: itemId(handle),
    name: candidate.name.trim() || handle || '未命名项目',
    handle,
    siteUrl: site,
    sites: site ? [site] : [],
    sitesSynced: false,
    xUrl: '',
    chain: '',
    ca,
    caChain,
    notes: '',
    push: true,
    pinnedAt,
    updatedAt: pinnedAt,
    origin: 'catalog',
  })
  commit(list, clearTombstone(handle))
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
    const nextName = name || prev.name
    const nextSite = siteUrl || prev.siteUrl
    const nextCa = ca || prev.ca
    const nextCaChain = caChain || prev.caChain
    const syncedChanged = nextName !== prev.name || handle !== prev.handle || nextSite !== prev.siteUrl
    const localChanged = nextCa !== prev.ca || nextCaChain !== prev.caChain
    const tomb = tombstones.find((entry) => entry.handle === handleKey(handle))
    const reaffirm = Boolean(tomb && timestampMs(tomb.removedAt) > timestampMs(prev.updatedAt || prev.pinnedAt))
    if (!syncedChanged && !localChanged && !reaffirm) return 'updated'
    const sites =
      siteUrl && siteUrl !== prev.siteUrl ? [siteUrl, ...prev.sites.filter((url) => url !== siteUrl)] : prev.sites
    list[index] = {
      ...prev,
      name: nextName,
      handle,
      siteUrl: nextSite,
      sites,
      sitesSynced: siteUrl !== prev.siteUrl ? false : prev.sitesSynced,
      ca: nextCa,
      caChain: nextCaChain,
      updatedAt: syncedChanged || reaffirm ? nowIso() : prev.updatedAt,
    }
    commit(list, syncedChanged || reaffirm ? clearTombstone(handle) : tombstones)
    return 'updated'
  }
  const pinnedAt = nowIso()
  list.unshift({
    id: itemId(handle),
    name: name || handle,
    handle,
    siteUrl,
    sites: siteUrl ? [siteUrl] : [],
    sitesSynced: false,
    xUrl: '',
    chain: '',
    ca,
    caChain,
    notes: '',
    push: true,
    pinnedAt,
    updatedAt: pinnedAt,
    origin: input.origin ?? 'manual',
  })
  commit(list, clearTombstone(handle))
  return 'added'
}

function fillEmptyCa(handle: string, ca: string, caChain: string): void {
  const nextCa = ca.trim().slice(0, 200)
  const nextChain = caChain.trim().slice(0, 80)
  if (!nextCa && !nextChain) return
  const list = items.slice()
  const index = indexByHandle(list, handle)
  if (index < 0) return
  const prev = list[index]
  const filledCa = prev.ca || nextCa
  const filledChain = prev.caChain || nextChain
  if (filledCa === prev.ca && filledChain === prev.caChain) return
  list[index] = { ...prev, ca: filledCa, caChain: filledChain }
  commit(list, tombstones)
}

export function pinObserved(input: {
  name: string
  handle: string
  candidate?: Candidate | null
  ca?: string
  caChain?: string
}): PinResult {
  if (input.candidate) {
    const result = pinCandidate(input.candidate)
    fillEmptyCa(input.candidate.handle || input.handle, input.ca ?? '', input.caChain ?? '')
    return result
  }
  return pinManual({
    name: input.name,
    handle: input.handle,
    siteUrl: '',
    ca: input.ca ?? '',
    caChain: input.caChain ?? '',
    origin: 'catalog',
  })
}

export function updateWorkbenchNotes(id: string, notes: string): void {
  const index = items.findIndex((item) => item.id === id)
  const trimmed = notes.slice(0, 20_000)
  if (index < 0 || items[index].notes === trimmed) return
  const next = items.slice()
  next[index] = { ...next[index], notes: trimmed, updatedAt: nowIso() }
  commit(next, clearTombstone(next[index].handle))
}

export function setWorkbenchPush(id: string, push: boolean): void {
  const index = items.findIndex((item) => item.id === id)
  if (index < 0 || items[index].push === push) return
  const next = items.slice()
  next[index] = { ...next[index], push, updatedAt: nowIso() }
  commit(next, clearTombstone(next[index].handle))
}

export function removeWorkbenchItem(id: string): void {
  removeWorkbenchItems([id])
}

export function removeWorkbenchItems(ids: Iterable<string>): void {
  const drop = new Set(ids)
  if (drop.size === 0) return
  const now = nowIso()
  let removed = tombstones
  const next: WorkbenchItem[] = []
  let changed = false
  for (const item of items) {
    if (!drop.has(item.id)) {
      next.push(item)
      continue
    }
    changed = true
    if (handleKey(item.handle)) removed = upsertTombstoneList(removed, item.handle, now)
  }
  if (!changed) return
  commit(next, removed)
}

function upsertTombstoneList(list: WorkbenchTombstone[], handle: string, removedAt: string): WorkbenchTombstone[] {
  const key = handleKey(handle)
  if (!key) return list
  const prev = list.find((entry) => entry.handle === key)
  if (prev && timestampMs(prev.removedAt) > timestampMs(removedAt)) return list
  return [...list.filter((entry) => entry.handle !== key), { handle: key, removedAt }]
}

/**
 * Drop pins whose handle is already launched. Writes localStorage the same way as a manual 移出.
 * Pins with no handle, and pins whose handle is not in the set, stay.
 * Returns how many pins were removed.
 */
export function removeLaunchedWorkbenchItems(handles: Iterable<string>): number {
  const launched = new Set<string>()
  for (const handle of handles) {
    const key = handleKey(handle)
    if (key) launched.add(key)
  }
  if (launched.size === 0) return 0
  const ids: string[] = []
  for (const item of items) {
    const key = handleKey(item.handle)
    if (key && launched.has(key)) ids.push(item.id)
  }
  if (ids.length === 0) return 0
  removeWorkbenchItems(ids)
  announceAutoRemove(ids.length)
  return ids.length
}

export function replaceWorkbench(next: WorkbenchItem[]): void {
  const now = nowIso()
  const stamped = next.map((item) => ({
    ...item,
    pinnedAt: item.pinnedAt || now,
    updatedAt: now,
  }))
  const kept = new Set(stamped.map((item) => handleKey(item.handle)).filter(Boolean))
  let removed = tombstones.filter((entry) => !kept.has(entry.handle))
  for (const item of items) {
    const key = handleKey(item.handle)
    if (!key || kept.has(key)) continue
    removed = upsertTombstoneList(removed, key, now)
  }
  commit(stamped, removed)
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
