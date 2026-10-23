/**
 * Live workbench reminder feed.
 * Hello snapshots replace the list. Incremental rows prepend by id.
 * While the workbench socket is down, GET /v1/workbench/alerts every 60s.
 */

import { getWorkbenchItems, handleKey } from './workbench'
import {
  ALERT_POLL_MS,
  ALERT_UI,
  loadStoredWorkbenchAlerts,
  mergeAlertIncremental,
  normalizeAlertList,
  planFreshAlert,
  reminderCanFlash,
  toastSummary,
  WB_ALERTS_STORAGE_KEY,
  type WorkbenchAlert,
} from './workbenchAlerts'
import { fetchWorkbenchAlerts, getApiSettings, isAuthError, resolveApiBase } from './workbenchApi'
import type { SocketEvent } from './workbenchSocket'

export interface WorkbenchToast {
  id: string
  handle: string
  summary: string
}

export interface WorkbenchAlertSnapshot {
  alerts: readonly WorkbenchAlert[]
  readIds: ReadonlySet<string>
  /** Handles that still have at least one blinking alert. */
  unread: ReadonlySet<string>
  highlightUntil: Readonly<Record<string, number>>
  toasts: readonly WorkbenchToast[]
}

const TOAST_MS = 12_000
const TOAST_LIMIT = 4

const READ_ID_LIMIT = 500

const EMPTY_SNAPSHOT: WorkbenchAlertSnapshot = {
  alerts: [],
  readIds: new Set<string>(),
  unread: new Set<string>(),
  highlightUntil: {},
  toasts: [],
}

let alerts: WorkbenchAlert[] = []
let readIds = new Set<string>()
let backlogQuiet = false
let highlightUntil: Record<string, number> = {}
let toasts: WorkbenchToast[] = []
let snapshot: WorkbenchAlertSnapshot = EMPTY_SNAPSHOT
const listeners = new Set<() => void>()
const toastTimers = new Map<string, number>()

let socketOpen = false
let polling = false
let authBlocked = false
let pollTimer = 0
let pullGen = 0
let lastPollAt = 0

function storageGet(): string | null {
  if (typeof localStorage === 'undefined') return null
  try {
    return localStorage.getItem(WB_ALERTS_STORAGE_KEY)
  } catch {
    return null
  }
}

function storageSet(value: string) {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(WB_ALERTS_STORAGE_KEY, value)
  } catch {
    // Keep the in-memory feed if the browser refuses the write.
  }
}

function unreadHandles(): Set<string> {
  const next = new Set<string>()
  for (const alert of alerts) {
    if (!alert.id || readIds.has(alert.id) || !reminderCanFlash(alert)) continue
    const key = handleKey(alert.handle)
    if (key) next.add(key)
  }
  return next
}

function trimReadIds() {
  if (readIds.size <= READ_ID_LIMIT) return
  const live = new Set(alerts.map((alert) => alert.id))
  const kept: string[] = []
  const extra: string[] = []
  for (const id of readIds) {
    if (live.has(id)) kept.push(id)
    else extra.push(id)
  }
  const room = Math.max(0, READ_ID_LIMIT - Math.min(kept.length, READ_ID_LIMIT))
  readIds = new Set([...kept.slice(-READ_ID_LIMIT), ...extra.slice(-room)])
}

function rememberRead(ids: Iterable<string>): boolean {
  let changed = false
  for (const id of ids) {
    if (!id || readIds.has(id)) continue
    readIds.add(id)
    changed = true
  }
  if (!changed) return false
  trimReadIds()
  return true
}

function persist() {
  storageSet(JSON.stringify({ alerts, readIds: [...readIds] }))
}

function publish() {
  snapshot = {
    alerts,
    readIds: new Set(readIds),
    unread: unreadHandles(),
    highlightUntil: { ...highlightUntil },
    toasts,
  }
  for (const listener of listeners) listener()
}

function hydrate() {
  const stored = loadStoredWorkbenchAlerts(storageGet())
  alerts = stored.alerts
  readIds = new Set(stored.readIds)
  backlogQuiet = stored.seeded
  publish()
}

hydrate()

function dismissTimer(id: string) {
  const timer = toastTimers.get(id)
  if (timer == null || typeof window === 'undefined') return
  window.clearTimeout(timer)
  toastTimers.delete(id)
}

export function dismissWorkbenchToast(id: string) {
  if (!toasts.some((toast) => toast.id === id)) return
  dismissTimer(id)
  toasts = toasts.filter((toast) => toast.id !== id)
  publish()
}

function noteFresh(alert: WorkbenchAlert, now: number) {
  const plan = planFreshAlert(alert, now)
  if (!plan.unread) return
  const key = handleKey(alert.handle)
  if (!key) return
  highlightUntil = { ...highlightUntil, [key]: plan.highlightUntil }
  if (!plan.toast) return
  const pinned = getWorkbenchItems().some((item) => handleKey(item.handle) === key)
  if (!pinned) return
  if (toasts.some((toast) => toast.id === alert.id)) return
  const summary = toastSummary(alert)
  toasts = [{ id: alert.id, handle: alert.handle, summary: summary || ALERT_UI.fallbackToast }, ...toasts].slice(0, TOAST_LIMIT)
  if (typeof window === 'undefined') return
  dismissTimer(alert.id)
  toastTimers.set(
    alert.id,
    window.setTimeout(() => dismissWorkbenchToast(alert.id), TOAST_MS),
  )
}

function replaceAlerts(next: readonly WorkbenchAlert[]) {
  const normalized = normalizeAlertList(next)
  if (!backlogQuiet) {
    for (const alert of normalized) {
      if (alert.id) readIds.add(alert.id)
    }
    backlogQuiet = true
  }
  alerts = normalized
  trimReadIds()
  persist()
  publish()
}

export function ingestWorkbenchSocketEvent(event: SocketEvent) {
  if (event.kind === 'alerts_snapshot') {
    replaceAlerts(event.alerts)
    return
  }
  if (event.kind !== 'alerts_incremental') return
  const merged = mergeAlertIncremental(alerts, event.alerts)
  alerts = merged.alerts
  const now = Date.now()
  for (const alert of merged.added) noteFresh(alert, now)
  persist()
  publish()
}

export function markWorkbenchAlertsRead(handle: string) {
  const key = handleKey(handle)
  if (!key) return
  const ids = alerts.filter((alert) => handleKey(alert.handle) === key).map((alert) => alert.id)
  if (!rememberRead(ids)) return
  if (highlightUntil[key] != null) {
    const next = { ...highlightUntil }
    delete next[key]
    highlightUntil = next
  }
  persist()
  publish()
}

/** Stop blinking for these alert ids. A click on the console passes every flashing id. */
export function markWorkbenchAlertIdsRead(ids: readonly string[]) {
  if (!rememberRead(ids)) return
  persist()
  publish()
}

export function getWorkbenchAlertSnapshot(): WorkbenchAlertSnapshot {
  return snapshot
}

export function getServerWorkbenchAlertSnapshot(): WorkbenchAlertSnapshot {
  return EMPTY_SNAPSHOT
}

export function subscribeWorkbenchAlerts(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

async function pull() {
  if (!polling || socketOpen || authBlocked) return
  const settings = getApiSettings()
  const token = settings.token.trim()
  if (!token) return
  const now = Date.now()
  if (now - lastPollAt < ALERT_POLL_MS) return
  lastPollAt = now
  const gen = ++pullGen
  try {
    const next = await fetchWorkbenchAlerts(resolveApiBase(settings.baseUrl), token)
    if (!polling || socketOpen || gen !== pullGen) return
    replaceAlerts(next)
  } catch (error) {
    if (isAuthError(error)) authBlocked = true
  }
}

function onStorage(event: StorageEvent) {
  if (event.key != null && event.key !== WB_ALERTS_STORAGE_KEY) return
  const stored = loadStoredWorkbenchAlerts(storageGet())
  alerts = stored.alerts
  readIds = new Set(stored.readIds)
  if (stored.seeded) backlogQuiet = true
  publish()
}

export function setWorkbenchAlertsSocketOpen(open: boolean) {
  if (socketOpen === open) return
  socketOpen = open
  if (open) {
    pullGen += 1
    return
  }
  void pull()
}

export function noteWorkbenchAlertSettingsChanged() {
  authBlocked = false
  lastPollAt = 0
  void pull()
}

export function startWorkbenchAlertPolling() {
  if (polling || typeof window === 'undefined') return
  polling = true
  window.addEventListener('storage', onStorage)
  pollTimer = window.setInterval(() => {
    void pull()
  }, ALERT_POLL_MS)
  void pull()
}

export function stopWorkbenchAlertPolling() {
  polling = false
  pullGen += 1
  if (typeof window === 'undefined') return
  window.clearInterval(pollTimer)
  pollTimer = 0
  window.removeEventListener('storage', onStorage)
}
