import { sortLaunchedItems, type LaunchedDocument, type LaunchedItem } from './launched'
import { pinHandleKey } from './syncMerge'

export interface ManualMark {
  handle: string
  name: string
  reason: string
  at: string
}

interface BlockEntry extends ManualMark {
  manual: boolean
  /** Present on the last `GET /v1/launched/recent`. */
  fromRecent: boolean
  /** Present on the last `GET /v1/workbench/blocklist`. */
  fromBlock: boolean
}

export interface BlockSnapshot {
  handles: readonly string[]
  manual: readonly ManualMark[]
}

const STORAGE_KEY = 'pad-hunter.manual-launched.v1'
const EMPTY_SNAPSHOT: BlockSnapshot = { handles: [], manual: [] }

const entries = new Map<string, BlockEntry>()
let snapshot: BlockSnapshot = EMPTY_SNAPSHOT
const listeners = new Set<() => void>()

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

export function siteClientIdFrom(deviceId: string): string {
  const id = deviceId.trim()
  if (!id) return ''
  return id.startsWith('site-') ? id : `site-${id}`
}

/** Body for `POST /v1/launched/mark`. */
export function launchedMarkBody(input: {
  handle: string
  name?: string
  at?: string
  clientId: string
}): Record<string, string> {
  const body: Record<string, string> = {
    handle: input.handle.replace(/^@/, '').trim(),
    reason: 'manual',
    source: 'manual',
    client_id: input.clientId,
  }
  const name = input.name?.trim()
  if (name) body.name = name
  const at = input.at?.trim()
  if (at) body.at = at
  return body
}

function isManualReason(reason: string): boolean {
  const key = reason.trim().toLowerCase()
  return key === 'manual' || key === '手动'
}

function markFrom(raw: unknown): ManualMark | null {
  if (typeof raw === 'string' || typeof raw === 'number') {
    const handle = pinHandleKey(String(raw))
    if (!handle) return null
    return { handle, name: handle, reason: '', at: '' }
  }
  const row = asRecord(raw)
  if (!row) return null
  const handle = pinHandleKey(asString(row.handle ?? row.twitter ?? row.x))
  if (!handle) return null
  return {
    handle,
    name: asString(row.name || row.project) || handle,
    reason: asString(row.reason || row.source),
    at: asString(row.at || row.marked_at || row.markedAt || row.removed_at || row.removedAt),
  }
}

function listFrom(value: unknown): ManualMark[] {
  if (!Array.isArray(value)) return []
  const out: ManualMark[] = []
  for (const entry of value) {
    const mark = markFrom(entry)
    if (mark) out.push(mark)
  }
  return out
}

function takeLists(row: Record<string, unknown>, keys: string[]): ManualMark[] {
  const out: ManualMark[] = []
  for (const key of keys) out.push(...listFrom(row[key]))
  return out
}

function dedupe(marks: ManualMark[]): ManualMark[] {
  const map = new Map<string, ManualMark>()
  for (const mark of marks) {
    const prev = map.get(mark.handle)
    if (!prev) {
      map.set(mark.handle, mark)
      continue
    }
    map.set(mark.handle, {
      handle: mark.handle,
      name: mark.name && mark.name !== mark.handle ? mark.name : prev.name,
      reason: isManualReason(mark.reason) ? prev.reason || mark.reason : mark.reason || prev.reason,
      at: mark.at || prev.at,
    })
  }
  return [...map.values()]
}

/** `GET /v1/launched/recent`. `null` when the body is not a mark list. */
export function parseLaunchedRecent(data: unknown): ManualMark[] | null {
  if (Array.isArray(data)) return dedupe(listFrom(data))
  const row = asRecord(data)
  if (!row) return null
  const keys = ['marks', 'items', 'recent', 'manual', 'manual_marks', 'list']
  if (!keys.some((key) => key in row) && !('mark' in row)) return null
  const marks = takeLists(row, keys)
  const one = markFrom(row.mark)
  if (one) marks.push(one)
  return dedupe(marks)
}

/** `GET /v1/workbench/blocklist`, or a blocklist object on the socket. */
export function parseBlocklist(data: unknown): { handles: string[]; marks: ManualMark[] } | null {
  const row = asRecord(data)
  if (!row) return null
  const state = asRecord(row.state) ?? row
  const keys = ['handles', 'items', 'blocklist', 'blocked', 'entries', 'list', 'manual', 'manual_marks', 'marks']
  const known =
    keys.some((key) => key in state) ||
    'manual_count' in state ||
    'manual_updated_at' in state ||
    'blocklist_count' in state
  if (!known) return null
  const marks = dedupe(takeLists(state, keys))
  return { handles: marks.map((mark) => mark.handle), marks }
}

/** POST response or a `launched_mark` socket payload. */
export function parseLaunchedMarkPayload(data: unknown): { marks: ManualMark[]; pins: unknown } | null {
  const row = asRecord(data)
  if (!row) return null
  const marks: ManualMark[] = []
  const one = markFrom(row.mark)
  if (one) marks.push(one)
  marks.push(...listFrom(row.dropped_launched ?? row.droppedLaunched))
  const nested = parseLaunchedRecent(row.launched)
  if (nested) marks.push(...nested)
  else marks.push(...listFrom(row.launched))
  const block = parseBlocklist(row.blocklist)
  if (block) marks.push(...block.marks)
  if (marks.length === 0 && row.ok !== true && row.mark == null && row.launched == null && row.blocklist == null) return null
  return { marks: dedupe(marks), pins: row.pins }
}

function toMark(entry: BlockEntry): ManualMark {
  return { handle: entry.handle, name: entry.name, reason: entry.reason, at: entry.at }
}

function publish() {
  const list = [...entries.values()].sort((a, b) => a.handle.localeCompare(b.handle))
  const next: BlockSnapshot = {
    handles: list.map((entry) => entry.handle),
    manual: list.filter((entry) => entry.manual).map(toMark),
  }
  if (sameSnapshot(snapshot, next)) return
  snapshot = next.handles.length === 0 && next.manual.length === 0 ? EMPTY_SNAPSHOT : next
  persist()
  for (const listener of listeners) listener()
}

function sameSnapshot(a: BlockSnapshot, b: BlockSnapshot): boolean {
  if (a.handles.length !== b.handles.length || a.manual.length !== b.manual.length) return false
  for (let i = 0; i < a.handles.length; i += 1) if (a.handles[i] !== b.handles[i]) return false
  for (let i = 0; i < a.manual.length; i += 1) {
    const left = a.manual[i]
    const right = b.manual[i]
    if (!left || !right) return false
    if (left.handle !== right.handle || left.name !== right.name || left.reason !== right.reason || left.at !== right.at) return false
  }
  return true
}

function persist() {
  if (typeof localStorage === 'undefined') return
  try {
    const list = [...entries.values()]
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, entries: list }))
  } catch {
    // The in-memory filter still hides the card in this tab.
  }
}

function load() {
  if (typeof localStorage === 'undefined') return
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw) as unknown
    const row = asRecord(parsed)
    const list = Array.isArray(row?.entries) ? row.entries : []
    for (const entry of list) {
      const mark = markFrom(entry)
      if (!mark) continue
      const record = asRecord(entry)
      const manual = record?.manual === true || isManualReason(mark.reason)
      entries.set(mark.handle, {
        ...mark,
        manual,
        fromRecent: record?.fromRecent === false ? false : manual || record?.fromRecent === true,
        fromBlock: record?.fromBlock !== false,
      })
    }
    publish()
  } catch {
    entries.clear()
  }
}

load()

export function getBlockSnapshot(): BlockSnapshot {
  return snapshot
}

export function getServerBlockSnapshot(): BlockSnapshot {
  return EMPTY_SNAPSHOT
}

export function subscribeBlocklist(listener: () => void): () => void {
  listeners.add(listener)
  const onStorage = (event: StorageEvent) => {
    if (event.key != null && event.key !== STORAGE_KEY) return
    entries.clear()
    load()
    listener()
  }
  if (typeof window !== 'undefined') window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(listener)
    if (typeof window !== 'undefined') window.removeEventListener('storage', onStorage)
  }
}

/** True while a confirm or socket notice is waiting for GET to echo it. */
export function isLocalLaunchHold(handle: string): boolean {
  const entry = readBlockEntry(handle)
  return Boolean(entry && !entry.fromRecent && !entry.fromBlock)
}

export function readBlockEntry(handle: string): BlockEntry | null {
  const key = pinHandleKey(handle)
  if (!key) return null
  const entry = entries.get(key)
  return entry ? { ...entry } : null
}

export function restoreBlockEntry(handle: string, previous: BlockEntry | null): void {
  const key = pinHandleKey(handle)
  if (!key) return
  if (previous) entries.set(key, { ...previous, handle: key })
  else entries.delete(key)
  publish()
}

/**
 * A socket or POST notice. Marks the server lists have not echoed yet stay local,
 * so an older poll cannot put the project back on 即将开盘, 项目推送, or the workbench.
 * A mark already echoed by GET keeps its server flags.
 */
export function ingestLaunchNotice(marks: readonly ManualMark[]): void {
  const fresh: ManualMark[] = []
  const echoed: ManualMark[] = []
  for (const mark of marks) {
    const prev = readBlockEntry(mark.handle)
    if (prev && (prev.fromRecent || prev.fromBlock)) echoed.push(mark)
    else fresh.push(mark)
  }
  if (fresh.length > 0) ingestBlocked(fresh, false, 'local')
  if (echoed.length > 0) ingestBlocked(echoed, false, 'block')
}

/** Drop one handle immediately. Used by `launched_unmark` before the list refetch. */
export function releaseBlocked(handle: string): void {
  const key = pinHandleKey(handle)
  if (!key || !entries.delete(key)) return
  publish()
}

/** Union into the hard filter. `forceManual` marks every row as a manual launch. */
export function ingestBlocked(
  marks: readonly ManualMark[],
  forceManual: boolean,
  source: 'recent' | 'block' | 'local' = forceManual ? 'recent' : 'block',
): void {
  let changed = false
  for (const mark of marks) {
    const handle = pinHandleKey(mark.handle)
    if (!handle) continue
    const manual = forceManual || isManualReason(mark.reason)
    const prev = entries.get(handle)
    const next: BlockEntry = {
      handle,
      name: (mark.name && mark.name !== handle ? mark.name : prev?.name) || mark.name || handle,
      reason: manual ? 'manual' : mark.reason || prev?.reason || '',
      at: mark.at || prev?.at || '',
      manual: manual || prev?.manual === true,
      fromRecent: source === 'recent' || (source === 'local' ? false : prev?.fromRecent === true),
      fromBlock: source === 'block' || (source === 'local' ? false : prev?.fromBlock === true),
    }
    if (source === 'local') {
      next.fromRecent = false
      next.fromBlock = false
    }
    if (
      prev &&
      prev.name === next.name &&
      prev.reason === next.reason &&
      prev.at === next.at &&
      prev.manual === next.manual &&
      prev.fromRecent === next.fromRecent &&
      prev.fromBlock === next.fromBlock
    ) {
      continue
    }
    entries.set(handle, next)
    changed = true
  }
  if (changed) publish()
}

/**
 * Replace one or both server lists. A handle that the refetched lists no longer
 * contain is dropped, so `launched_unmark` can bring the card back.
 * `null` means that request failed and its previous rows stay.
 * Rows still waiting on POST (`local`) stay until the server copy arrives.
 */
export function applyServerBlocks(update: { recent: ManualMark[] | null; block: ManualMark[] | null }): void {
  if (update.recent == null && update.block == null) return
  const recentKeys = update.recent ? new Set(update.recent.map((mark) => pinHandleKey(mark.handle)).filter(Boolean)) : null
  const blockKeys = update.block ? new Set(update.block.map((mark) => pinHandleKey(mark.handle)).filter(Boolean)) : null
  for (const [key, entry] of entries) {
    const localOnly = !entry.fromRecent && !entry.fromBlock
    if (localOnly) continue
    const keepRecent = recentKeys ? recentKeys.has(key) : entry.fromRecent
    const keepBlock = blockKeys ? blockKeys.has(key) : entry.fromBlock
    if (!keepRecent && !keepBlock) entries.delete(key)
    else {
      entry.fromRecent = keepRecent
      entry.fromBlock = keepBlock
    }
  }
  if (update.recent) ingestBlocked(update.recent, true, 'recent')
  if (update.block) ingestBlocked(update.block, false, 'block')
  publish()
}

export function handlesFromMarks(marks: readonly ManualMark[]): string[] {
  return [...new Set(marks.map((mark) => pinHandleKey(mark.handle)).filter(Boolean))]
}

/** Manual marks that Pages has not archived yet. `listingAt` stays null. */
export function withManualLaunched(doc: LaunchedDocument, marks: readonly ManualMark[]): LaunchedDocument {
  const seen = new Set(doc.items.map((item) => pinHandleKey(item.handle)).filter(Boolean))
  const extra: LaunchedItem[] = []
  for (const mark of marks) {
    const handle = pinHandleKey(mark.handle)
    if (!handle || seen.has(handle)) continue
    seen.add(handle)
    extra.push({
      project: mark.name || handle,
      handle,
      chain: '',
      category: '',
      xUrl: '',
      sites: [],
      listingAt: null,
      ca: null,
      caChain: null,
      reason: 'manual',
      evidence: '',
      removedAt: mark.at,
    })
  }
  if (extra.length === 0) return { ...doc, items: sortLaunchedItems(doc.items) }
  return { ...doc, count: doc.items.length + extra.length, items: sortLaunchedItems([...extra, ...doc.items]) }
}
