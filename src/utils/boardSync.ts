/**
 * Cross-device sync for workbench pins and 「已看」 marks.
 * With a token: pull on connect, every 25s, and when the window is focused,
 * merge last-write-wins, then push local edits. A 404 means the old backend:
 * pins fall back to a non-empty full replace, and reviewed marks stay on this device.
 */

import type { Candidate } from '../types'
import { findByHandle } from './candidates'
import {
  chainForPin,
  errorText,
  fetchPins,
  fetchReviewed,
  getApiSettings,
  isAuthError,
  isNotFound,
  pushMergedPins,
  pushMergedReviewed,
  resolveApiBase,
  sitesForPin,
  subscribeApiSettings,
  syncItemsFromPins,
  syncWorkbench,
  xUrlForPin,
} from './workbenchApi'
import {
  getReviewedSyncMarks,
  isReviewedWriteSuppressed,
  replaceReviewedMarks,
  subscribeReviewed,
  type ReviewMark,
} from './reviewed'
import {
  mergePins,
  mergeReviewed,
  nowIso,
  pinHandleKey,
  pinsNeedPush,
  reviewsNeedPush,
  timestampMs,
  withDroppedHandles,
  type PinMergeState,
  type PinWire,
  type ReviewWire,
} from './syncMerge'
import {
  applyIntegratedPins,
  getWorkbenchItems,
  getWorkbenchTombstones,
  handleKey,
  isPinApplySilent,
  normalizeHandle,
  removeLaunchedWorkbenchItems,
  subscribeWorkbench,
  workbenchItemFromWire,
  type WorkbenchItem,
  type WorkbenchTombstone,
} from './workbench'

const PULL_MS = 25_000
const PUSH_MS = 500

export interface BoardSyncStatus {
  phase: 'idle' | 'syncing' | 'ok' | 'error'
  message: string | null
  hint: '' | '已同步' | '同步失败，仅本机'
  authError: boolean
}

const IDLE_STATUS: BoardSyncStatus = { phase: 'idle', message: null, hint: '', authError: false }

let status: BoardSyncStatus = IDLE_STATUS
const listeners = new Set<() => void>()

let users = 0
let session = 0
let catalog: Candidate[] = []
let catalogReady = false
let pinHold = false

let pinsLegacy = false
let reviewedLegacy = false
let pinsProbed = false
let reviewedProbed = false
let lastRemotePins: PinMergeState | null = null
let lastRemoteReviews: Record<string, ReviewWire> | null = null
let lastLegacyPayload = ''

let pinError: string | null = null
let reviewError: string | null = null
let pinOk = false
let reviewOk = false
let authFailed = false
let pinCount: number | null = null
let loud = 0

let pinTimer = 0
let reviewTimer = 0
let pullTimer = 0
let pullQuiet = true
let interval = 0
let pinLock: Promise<void> = Promise.resolve()
let reviewLock: Promise<void> = Promise.resolve()
let unsubs: Array<() => void> = []
let onWake: (() => void) | null = null

export function getBoardSyncStatus(): BoardSyncStatus {
  return status
}

export function getBoardSyncServerStatus(): BoardSyncStatus {
  return IDLE_STATUS
}

export function subscribeBoardSync(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function setBoardSyncCatalog(next: Candidate[], ready: boolean): void {
  catalog = next
  const becameReady = ready && !catalogReady
  catalogReady = ready
  if (becameReady && pinHold && users > 0) schedulePinPush()
}

export function startBoardSync(): () => void {
  users += 1
  if (users === 1) arm()
  return () => {
    users -= 1
    if (users === 0) disarm()
  }
}

function publishStatus() {
  const token = currentAuth().token
  let hint: BoardSyncStatus['hint'] = ''
  if (token && (pinError || reviewError)) hint = '同步失败，仅本机'
  else if (token && (pinOk || reviewOk)) hint = '已同步'
  const phase: BoardSyncStatus['phase'] = !token
    ? 'idle'
    : loud > 0
      ? 'syncing'
      : pinError || reviewError
        ? 'error'
        : pinOk || reviewOk
          ? 'ok'
          : 'idle'
  let message: string | null = null
  if (pinError) message = pinError
  else if (reviewError) message = reviewError
  else if (pinOk && pinCount != null) message = `已同步 ${pinCount} 个目标`
  const next: BoardSyncStatus = { phase, message, hint, authError: Boolean(token) && authFailed }
  if (
    next.phase === status.phase &&
    next.message === status.message &&
    next.hint === status.hint &&
    next.authError === status.authError
  ) {
    return
  }
  status = next
  for (const listener of listeners) listener()
}

function currentAuth(): { token: string; base: string } {
  const settings = getApiSettings()
  return { token: settings.token.trim(), base: resolveApiBase(settings.baseUrl) }
}

function sessionAlive(id: number): boolean {
  return id === session && users > 0
}

function authChanged(token: string, base: string): boolean {
  const current = currentAuth()
  return current.token !== token || current.base !== base
}

function resetProbe() {
  pinsLegacy = false
  reviewedLegacy = false
  pinsProbed = false
  reviewedProbed = false
  lastRemotePins = null
  lastRemoteReviews = null
  lastLegacyPayload = ''
  pinHold = false
  pinError = null
  reviewError = null
  pinOk = false
  reviewOk = false
  authFailed = false
  pinCount = null
}

function begin(quiet: boolean) {
  if (!quiet) loud += 1
  publishStatus()
}

function end(quiet: boolean) {
  if (!quiet) loud = Math.max(0, loud - 1)
  publishStatus()
}

function runLocked(lock: 'pin' | 'review', task: () => Promise<void>): Promise<void> {
  const previous = lock === 'pin' ? pinLock : reviewLock
  const run = previous.then(task, task)
  const settled = run.then(
    () => undefined,
    () => undefined,
  )
  if (lock === 'pin') pinLock = settled
  else reviewLock = settled
  return run
}

function wireFromItem(item: WorkbenchItem): PinWire | null {
  const handle = normalizeHandle(item.handle)
  if (!handle) return null
  const candidate = findByHandle(catalog, handle)
  const sites = item.sitesSynced ? item.sites : sitesForPin(item, candidate)
  return {
    handle,
    name: item.name.trim() || handle,
    sites,
    x_url: item.xUrl || xUrlForPin(item, candidate),
    chain: item.chain || chainForPin(item, candidate),
    notes: item.notes,
    push: item.push,
    added_at: item.pinnedAt,
    updated_at: item.updatedAt || item.pinnedAt,
  }
}

function currentPinState(): PinMergeState {
  const items: PinWire[] = []
  for (const item of getWorkbenchItems()) {
    const wire = wireFromItem(item)
    if (wire) items.push(wire)
  }
  return {
    items,
    removed: getWorkbenchTombstones().map((entry) => ({ handle: entry.handle, removed_at: entry.removedAt })),
  }
}

function orderPins(prev: WorkbenchItem[], built: WorkbenchItem[], noHandle: WorkbenchItem[]): WorkbenchItem[] {
  const nextByKey = new Map<string, WorkbenchItem>()
  for (const item of built) {
    const key = handleKey(item.handle)
    if (key) nextByKey.set(key, item)
  }
  const noHandleIds = new Set(noHandle.map((item) => item.id))
  const used = new Set<string>()
  const kept: WorkbenchItem[] = []
  for (const item of prev) {
    const key = handleKey(item.handle)
    if (!key) {
      if (noHandleIds.has(item.id)) kept.push(item)
      continue
    }
    const match = nextByKey.get(key)
    if (!match) continue
    kept.push(match)
    used.add(key)
  }
  const fresh: WorkbenchItem[] = []
  for (const [key, item] of nextByKey) {
    if (!used.has(key)) fresh.push(item)
  }
  return [...fresh, ...kept]
}

function integrateRemotePins(remote: PinMergeState): boolean {
  const localItems = getWorkbenchItems()
  const merged = mergePins(currentPinState(), remote)
  const remoteItems = new Map<string, PinWire>()
  for (const item of remote.items) {
    const key = pinHandleKey(item.handle)
    if (key) remoteItems.set(key, item)
  }
  const remoteTomb = new Map<string, number>()
  for (const tomb of remote.removed) {
    const key = pinHandleKey(tomb.handle)
    if (!key) continue
    remoteTomb.set(key, Math.max(remoteTomb.get(key) ?? 0, timestampMs(tomb.removed_at)))
  }
  const prevByHandle = new Map<string, WorkbenchItem>()
  for (const item of localItems) {
    const key = handleKey(item.handle)
    if (key && !prevByHandle.has(key)) prevByHandle.set(key, item)
  }
  const built: WorkbenchItem[] = []
  for (const wire of merged.items) {
    const key = pinHandleKey(wire.handle)
    const existing = key ? prevByHandle.get(key) : undefined
    const localAt = existing ? timestampMs(existing.updatedAt || existing.pinnedAt) : 0
    const remoteAt = key ? timestampMs(remoteItems.get(key)?.updated_at) : 0
    const tombAt = key ? (remoteTomb.get(key) ?? 0) : 0
    if (existing && localAt > remoteAt && localAt >= tombAt) built.push(existing)
    else built.push(workbenchItemFromWire(wire, existing))
  }
  const noHandle = localItems.filter((item) => !handleKey(item.handle))
  const removed: WorkbenchTombstone[] = merged.removed
    .map((entry) => ({ handle: pinHandleKey(entry.handle), removedAt: entry.removed_at }))
    .filter((entry) => entry.handle && entry.removedAt)
  applyIntegratedPins(orderPins(localItems, built, noHandle), removed)
  lastRemotePins = remote
  return pinsNeedPush(currentPinState(), remote)
}

function deferPinPush(): boolean {
  if (catalogReady) return false
  if (pinsLegacy) return getWorkbenchItems().some((item) => Boolean(handleKey(item.handle)) && !item.sitesSynced)
  const remoteAt = new Map<string, number>()
  const tombAt = new Map<string, number>()
  for (const item of lastRemotePins?.items ?? []) {
    const key = pinHandleKey(item.handle)
    if (key) remoteAt.set(key, timestampMs(item.updated_at))
  }
  for (const tomb of lastRemotePins?.removed ?? []) {
    const key = pinHandleKey(tomb.handle)
    if (key) tombAt.set(key, Math.max(tombAt.get(key) ?? 0, timestampMs(tomb.removed_at)))
  }
  return getWorkbenchItems().some((item) => {
    const key = handleKey(item.handle)
    if (!key || item.sitesSynced) return false
    const localAt = timestampMs(item.updatedAt || item.pinnedAt)
    return localAt > (remoteAt.get(key) ?? 0) && localAt >= (tombAt.get(key) ?? 0)
  })
}

function noteFailure(error: unknown, kind: 'pin' | 'review') {
  if (isAuthError(error)) authFailed = true
  const message = errorText(error)
  if (kind === 'pin') {
    pinError = message
    pinOk = false
  } else {
    reviewError = message
    reviewOk = false
  }
}

async function pullPinsBody(id: number, token: string, base: string, quiet: boolean) {
  if (!sessionAlive(id)) return
  begin(quiet)
  try {
    const remote = await fetchPins(base, token)
    if (!sessionAlive(id) || authChanged(token, base)) return
    pinsLegacy = false
    pinsProbed = true
    authFailed = false
    pinError = null
    const needsPush = integrateRemotePins(remote.state)
    pinCount = getWorkbenchItems().filter((item) => handleKey(item.handle)).length
    pinOk = true
    if (needsPush) schedulePinPush()
  } catch (error) {
    if (!sessionAlive(id) || authChanged(token, base)) return
    if (isNotFound(error)) {
      const firstLegacy = !pinsLegacy
      pinsLegacy = true
      pinsProbed = true
      pinError = null
      if (firstLegacy) schedulePinPush()
      return
    }
    noteFailure(error, 'pin')
  } finally {
    end(quiet)
  }
}

async function pushPinsBody() {
  const id = session
  const { token, base } = currentAuth()
  if (!sessionAlive(id) || !token) return
  if (!pinsProbed) {
    await pullPinsBody(id, token, base, false)
    return
  }
  if (deferPinPush()) {
    pinHold = true
    return
  }
  pinHold = false
  if (pinsLegacy) {
    const items = syncItemsFromPins(getWorkbenchItems(), catalog)
    if (items.length === 0) return
    const payload = JSON.stringify(items)
    if (payload === lastLegacyPayload) return
    begin(false)
    try {
      const result = await syncWorkbench(base, token, items)
      if (!sessionAlive(id) || authChanged(token, base)) return
      lastLegacyPayload = payload
      removeLaunchedWorkbenchItems(result.droppedLaunched)
      authFailed = false
      pinError = null
      pinOk = true
      pinCount = result.count
    } catch (error) {
      if (!sessionAlive(id) || authChanged(token, base)) return
      noteFailure(error, 'pin')
    } finally {
      end(false)
    }
    return
  }
  const sent = currentPinState()
  if (lastRemotePins && !pinsNeedPush(sent, lastRemotePins)) return
  if (sent.items.length === 0 && sent.removed.length === 0) return
  begin(false)
  try {
    const response = await pushMergedPins(base, token, sent)
    if (!sessionAlive(id) || authChanged(token, base)) return
    if (!response.state) {
      pinError = '接口返回的不是钉选列表'
      pinOk = false
      return
    }
    const reconciled = withDroppedHandles(sent, response.state, nowIso())
    const needsPush = integrateRemotePins(reconciled)
    removeLaunchedWorkbenchItems(response.droppedLaunched)
    authFailed = false
    pinError = null
    pinOk = true
    pinCount = getWorkbenchItems().filter((item) => handleKey(item.handle)).length
    if (needsPush) schedulePinPush()
  } catch (error) {
    if (!sessionAlive(id) || authChanged(token, base)) return
    if (isNotFound(error) && !pinsLegacy) {
      pinsLegacy = true
      schedulePinPush()
      return
    }
    noteFailure(error, 'pin')
  } finally {
    end(false)
  }
}

function currentReviewState(): Record<string, ReviewWire> {
  const marks: Record<string, ReviewWire> = {}
  for (const [key, mark] of Object.entries(getReviewedSyncMarks())) {
    marks[key] = reviewWire(mark)
  }
  return marks
}

function reviewWire(mark: ReviewMark): ReviewWire {
  return {
    at: mark.at,
    snapshot: {
      listingAt: mark.snapshot.listingAt,
      status: mark.snapshot.status,
      listing: mark.snapshot.listing,
      ca: mark.snapshot.ca,
    },
    cleared_at: mark.clearedAt ?? '',
  }
}

function marksFromWires(wires: Record<string, ReviewWire>): Record<string, ReviewMark> {
  const next: Record<string, ReviewMark> = {}
  for (const [key, wire] of Object.entries(wires)) {
    const id = key.trim().toLowerCase()
    if (!id) continue
    next[id] = {
      at: wire.at,
      snapshot: { ...wire.snapshot },
      ...(wire.cleared_at ? { clearedAt: wire.cleared_at } : {}),
    }
  }
  return next
}

function integrateRemoteReviews(remote: Record<string, ReviewWire>): boolean {
  const merged = mergeReviewed(currentReviewState(), remote)
  replaceReviewedMarks(marksFromWires(merged))
  lastRemoteReviews = remote
  return reviewsNeedPush(currentReviewState(), remote)
}

async function pullReviewsBody(id: number, token: string, base: string, quiet: boolean) {
  if (!sessionAlive(id)) return
  begin(quiet)
  try {
    const remote = await fetchReviewed(base, token)
    if (!sessionAlive(id) || authChanged(token, base)) return
    reviewedLegacy = false
    reviewedProbed = true
    authFailed = false
    reviewError = null
    const needsPush = integrateRemoteReviews(remote.marks)
    reviewOk = true
    if (needsPush) scheduleReviewPush()
  } catch (error) {
    if (!sessionAlive(id) || authChanged(token, base)) return
    if (isNotFound(error)) {
      reviewedLegacy = true
      reviewedProbed = true
      reviewError = null
      return
    }
    noteFailure(error, 'review')
  } finally {
    end(quiet)
  }
}

async function pushReviewsBody() {
  const id = session
  const { token, base } = currentAuth()
  if (!sessionAlive(id) || !token) return
  if (!reviewedProbed) {
    await pullReviewsBody(id, token, base, false)
    return
  }
  if (reviewedLegacy) return
  const sent = currentReviewState()
  if (lastRemoteReviews && !reviewsNeedPush(sent, lastRemoteReviews)) return
  if (!lastRemoteReviews && Object.keys(sent).length === 0) return
  begin(false)
  try {
    const returned = await pushMergedReviewed(base, token, sent)
    if (!sessionAlive(id) || authChanged(token, base)) return
    if (!returned) {
      reviewError = '接口返回的不是已看记录'
      reviewOk = false
      return
    }
    const needsPush = integrateRemoteReviews(returned)
    authFailed = false
    reviewError = null
    reviewOk = true
    if (needsPush) scheduleReviewPush()
  } catch (error) {
    if (!sessionAlive(id) || authChanged(token, base)) return
    if (isNotFound(error)) {
      reviewedLegacy = true
      reviewError = null
      return
    }
    noteFailure(error, 'review')
  } finally {
    end(false)
  }
}

function schedulePinPush() {
  if (users === 0) return
  window.clearTimeout(pinTimer)
  pinTimer = window.setTimeout(() => {
    void runLocked('pin', () => pushPinsBody())
  }, PUSH_MS)
}

function scheduleReviewPush() {
  if (users === 0) return
  window.clearTimeout(reviewTimer)
  reviewTimer = window.setTimeout(() => {
    void runLocked('review', () => pushReviewsBody())
  }, PUSH_MS)
}

function schedulePull(delay: number, quiet: boolean) {
  if (users === 0) return
  pullQuiet = pullQuiet && quiet
  window.clearTimeout(pullTimer)
  pullTimer = window.setTimeout(() => {
    const quietPull = pullQuiet
    pullQuiet = true
    const id = session
    const { token, base } = currentAuth()
    if (!token || !sessionAlive(id)) {
      publishStatus()
      return
    }
    void Promise.all([
      runLocked('pin', () => pullPinsBody(id, token, base, quietPull)),
      runLocked('review', () => pullReviewsBody(id, token, base, quietPull)),
    ])
  }, delay)
}

function onSettings() {
  resetProbe()
  publishStatus()
  if (currentAuth().token) schedulePull(0, false)
}

function arm() {
  session += 1
  onWake = () => {
    if (document.visibilityState === 'hidden') return
    schedulePull(200, true)
  }
  unsubs = [
    subscribeApiSettings(onSettings),
    subscribeWorkbench(() => {
      if (isPinApplySilent()) return
      schedulePinPush()
    }),
    subscribeReviewed(() => {
      if (isReviewedWriteSuppressed()) return
      scheduleReviewPush()
    }),
  ]
  window.addEventListener('focus', onWake)
  document.addEventListener('visibilitychange', onWake)
  interval = window.setInterval(() => {
    if (document.visibilityState === 'hidden') return
    schedulePull(0, true)
  }, PULL_MS)
  if (currentAuth().token) schedulePull(0, false)
  else publishStatus()
}

function disarm() {
  session += 1
  window.clearTimeout(pinTimer)
  window.clearTimeout(reviewTimer)
  window.clearTimeout(pullTimer)
  window.clearInterval(interval)
  interval = 0
  if (onWake) {
    window.removeEventListener('focus', onWake)
    document.removeEventListener('visibilitychange', onWake)
    onWake = null
  }
  for (const unsub of unsubs) unsub()
  unsubs = []
  loud = 0
  pullQuiet = true
  publishStatus()
}
