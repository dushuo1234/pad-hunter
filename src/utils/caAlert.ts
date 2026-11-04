import type { CaFind } from '../types'
import { reminderTitle } from './workbenchAlerts'
import { alertableFinds, caAddressId, displayProjectName } from './caFinds'
import { handleKey } from './workbench'
import type { FoundAddress, WorkbenchStatusItem } from './workbenchApi'

export const ALERT_PHRASE = '姐姐，微信来啦'
const SOUND_KEY = 'pad-hunter.ca-alert.sound'
const SEEN_KEY = 'pad-hunter.ca-alert.seen.v1'
const TOAST_LIMIT = 6
const TOAST_MS = 12000
const FLASH_MS = 900

export interface CaSighting {
  address: string
  project: string
  handle?: string
  statusZh?: string
  provenanceZh?: string
}

export interface CaToast {
  id: string
  project: string
  projectKey: string
  address: string
  statusZh: string
  provenanceZh: string
}

/**
 * Stable per-project identity for the "clicked once, never alert again"
 * rule. Handles win when present; the display name is the fallback.
 */
export function sightingProjectKey(sighting: { handle?: string; project: string }): string {
  const key = sighting.handle ? handleKey(sighting.handle) : ''
  if (key) return `h:${key}`
  return `p:${sighting.project.trim().toLowerCase()}`
}

interface AlertUi {
  enabled: boolean
  unlocked: boolean
  toasts: CaToast[]
}

type WatchSource = 'ca' | 'workbench'

interface SeenState {
  ids: Set<string>
  baselined: Record<WatchSource, boolean>
  /** Project keys the user has clicked once — never alert for them again. */
  acked: Set<string>
}

const EMPTY_TOASTS: CaToast[] = []

let ui: AlertUi = {
  enabled: loadEnabled(),
  unlocked: false,
  toasts: EMPTY_TOASTS,
}
let seen: SeenState = loadSeen()
let workbenchLiveMounted = 0
const detailPrimed = new Set<string>()
const uiListeners = new Set<() => void>()

let audio: HTMLAudioElement | null = null
let playGeneration = 0
let baseTitle = typeof document === 'undefined' ? '' : document.title
let flashing = false
let flashOn = false
let flashTimer = 0
let titleArmed = false
let toastSeq = 0
let queued: CaSighting[] = []
let flushScheduled = false

function loadEnabled(): boolean {
  if (typeof localStorage === 'undefined') return true
  try {
    return localStorage.getItem(SOUND_KEY) !== 'off'
  } catch {
    return true
  }
}

function loadSeen(): SeenState {
  const empty: SeenState = { ids: new Set(), baselined: { ca: false, workbench: false }, acked: new Set() }
  if (typeof localStorage === 'undefined') return empty
  try {
    const raw = localStorage.getItem(SEEN_KEY)
    if (!raw) return empty
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return empty
    const row = parsed as Record<string, unknown>
    const addresses = Array.isArray(row.addresses)
      ? row.addresses.filter((item): item is string => typeof item === 'string' && item.length > 0)
      : []
    const flags = row.baselined && typeof row.baselined === 'object' ? (row.baselined as Record<string, unknown>) : {}
    const acked = Array.isArray(row.acked)
      ? row.acked.filter((item): item is string => typeof item === 'string' && item.length > 0)
      : []
    return {
      ids: new Set(addresses),
      baselined: { ca: flags.ca === true, workbench: flags.workbench === true },
      acked: new Set(acked),
    }
  } catch {
    return empty
  }
}

function persistEnabled() {
  try {
    localStorage.setItem(SOUND_KEY, ui.enabled ? 'on' : 'off')
  } catch {
    // The toggle still works for this tab if storage is blocked.
  }
}

function persistSeen() {
  try {
    const payload = {
      addresses: [...seen.ids],
      baselined: seen.baselined,
      acked: [...seen.acked],
    }
    localStorage.setItem(SEEN_KEY, JSON.stringify(payload))
  } catch {
    // Keep the in-memory set so this tab does not re-alert.
  }
}

/** Remember that the user has dealt with this project: silence it for good. */
export function ackCaProject(handle: string, project = '') {
  const key = sightingProjectKey({ handle: handle || undefined, project })
  if (!key || seen.acked.has(key)) return
  seen.acked.add(key)
  persistSeen()
}

export function isCaProjectAcked(sighting: { handle?: string; project: string }): boolean {
  return seen.acked.has(sightingProjectKey(sighting))
}

function emitUi() {
  for (const listener of uiListeners) listener()
}

export function subscribeAlertUi(listener: () => void): () => void {
  uiListeners.add(listener)
  return () => uiListeners.delete(listener)
}

export function getAlertUi(): AlertUi {
  return ui
}

export function projectLabel(project: string, handle = ''): string {
  const name = project.trim()
  if (name) return name
  const normalized = handle.trim().replace(/^@/, '')
  if (normalized) return `@${normalized}`
  return '未命名项目'
}

export function sightingsFromFinds(finds: CaFind[]): CaSighting[] {
  return alertableFinds(finds).map((find) => ({
    address: find.address,
    project: displayProjectName(find.project, find.handle),
    handle: find.handle || undefined,
    statusZh: find.caStatusZh || '已确认CA',
    provenanceZh: find.provenanceZh,
  }))
}

export function sightingsFromStatus(items: WorkbenchStatusItem[]): CaSighting[] {
  const sightings: CaSighting[] = []
  for (const item of items) {
    if (item.alreadyListed) continue
    const project = projectLabel(item.name, item.handle)
    for (const address of item.lastAddresses) {
      sightings.push({ address, project, handle: item.handle || undefined })
    }
  }
  return sightings
}

export function sightingsFromDetail(project: string, handle: string, addresses: FoundAddress[]): CaSighting[] {
  return addresses.map((found) => ({
    address: found.address,
    project: projectLabel(found.label || project, handle),
    handle: handle || undefined,
  }))
}

function remember(sightings: CaSighting[]): boolean {
  let changed = false
  for (const sighting of sightings) {
    const id = caAddressId(sighting.address)
    if (!id || seen.ids.has(id)) continue
    seen.ids.add(id)
    changed = true
  }
  return changed
}

function takeNovel(sightings: CaSighting[]): CaSighting[] {
  const novel: CaSighting[] = []
  const batch = new Set<string>()
  for (const sighting of sightings) {
    const id = caAddressId(sighting.address)
    if (!id || seen.ids.has(id) || batch.has(id)) continue
    batch.add(id)
    seen.ids.add(id)
    novel.push({ address: sighting.address.trim(), project: sighting.project, handle: sighting.handle })
  }
  return novel
}

/**
 * First successful read of a source records current addresses and stays quiet.
 * Later reads alert once per address that was not stored yet.
 */
export function observeSightings(source: WatchSource, sightings: CaSighting[]) {
  const wasBaselined = seen.baselined[source]
  if (!wasBaselined) {
    remember(sightings)
    seen = { ...seen, baselined: { ...seen.baselined, [source]: true } }
    persistSeen()
    return
  }
  const novel = takeNovel(sightings)
  if (novel.length === 0) return
  persistSeen()
  // Projects the user already clicked once stay silent even when a brand
  // new address shows up for them; their addresses are still remembered
  // above so nothing replays if the ack is ever lifted.
  const fresh = novel.filter((sighting) => !isCaProjectAcked(sighting))
  if (fresh.length === 0) return
  queueNovel(fresh)
}

export function observeWorkbenchStatus(items: WorkbenchStatusItem[]) {
  const sightings = sightingsFromStatus(items)
  const withheld = items.some((item) => item.addressCount > 0 && item.lastAddresses.length === 0)
  if (!seen.baselined.workbench && sightings.length === 0 && withheld) return
  observeSightings('workbench', sightings)
}

/**
 * Detail is polled per project. The first snapshot in this tab only fills the seen set,
 * so opening a row does not replay addresses the status feed never listed.
 */
function detailAlertAddresses(addresses: FoundAddress[], launched: boolean): FoundAddress[] {
  if (launched) return []
  return addresses.filter((found) => !/扫出钱包|疑似山寨|非CA|非地址|NFT合约|未确认/.test(found.label))
}

export function observeWorkbenchDetail(
  handle: string,
  project: string,
  addresses: FoundAddress[],
  options?: { launched?: boolean },
) {
  // Opening a project's detail counts as having clicked it: from now on
  // this project never raises a CA sound/toast again, same rule as the
  // workbench alert console.
  ackCaProject(handle, project)
  const launched = options?.launched === true
  const silent = launched ? addresses : addresses.filter((found) => /扫出钱包|疑似山寨|非CA|非地址|NFT合约|未确认/.test(found.label))
  if (remember(sightingsFromDetail(project, handle, silent))) persistSeen()
  const key = handleKey(handle) || project.trim().toLowerCase()
  const sightings = sightingsFromDetail(project, handle, detailAlertAddresses(addresses, launched))
  const first = key ? !detailPrimed.has(key) : false
  if (key) detailPrimed.add(key)
  if (!seen.baselined.workbench) {
    observeSightings('workbench', sightings)
    return
  }
  if (first) {
    if (remember(sightings)) persistSeen()
    return
  }
  observeSightings('workbench', sightings)
}

function queueNovel(novel: CaSighting[]) {
  queued.push(...novel)
  if (flushScheduled) return
  flushScheduled = true
  queueMicrotask(flushNovel)
}

function flushNovel() {
  flushScheduled = false
  const batch = queued
  queued = []
  if (batch.length === 0) return
  pushToasts(batch)
  notifyDesktop(batch)
  armTitleFlash()
  if (ui.enabled) void playAlert()
}

function pushToasts(items: CaSighting[]) {
  const next = items.slice(0, TOAST_LIMIT).map((item) => ({
    id: `ca-${++toastSeq}`,
    project: item.project,
    projectKey: sightingProjectKey(item),
    address: item.address,
    statusZh: item.statusZh || '新CA',
    provenanceZh: item.provenanceZh || '',
  }))
  ui = { ...ui, toasts: [...ui.toasts, ...next].slice(-TOAST_LIMIT) }
  emitUi()
  for (const toast of next) {
    window.setTimeout(() => dismissToast(toast.id), TOAST_MS)
  }
}

export function dismissToast(id: string) {
  if (!ui.toasts.some((toast) => toast.id === id)) return
  ui = { ...ui, toasts: ui.toasts.filter((toast) => toast.id !== id) }
  emitUi()
}

/** Acknowledge every toast of this toast's project without dismissing. */
export function ackToastProject(id: string) {
  const toast = ui.toasts.find((item) => item.id === id)
  if (!toast || seen.acked.has(toast.projectKey)) return
  seen.acked.add(toast.projectKey)
  persistSeen()
}

/** The toast's close button: dismiss it and silence its project for good. */
export function ackToast(id: string) {
  ackToastProject(id)
  dismissToast(id)
}

function soundUrl(): string {
  const base = import.meta.env?.BASE_URL || '/'
  return `${base}sounds/new-ca.mp3`
}

function getAudio(): HTMLAudioElement {
  if (!audio) {
    audio = new Audio(soundUrl())
    audio.preload = 'auto'
  }
  return audio
}

function markUnlocked() {
  if (ui.unlocked) return
  ui = { ...ui, unlocked: true }
  emitUi()
}

function speakPhrase() {
  const synth = window.speechSynthesis
  if (!synth) return
  const utter = new SpeechSynthesisUtterance(ALERT_PHRASE)
  utter.lang = 'zh-CN'
  utter.rate = 1.05
  const voices = synth.getVoices()
  const voice =
    voices.find((item) => /zh-CN/i.test(item.lang) && /xiaoyi|xiaoxiao|xiaohan|female/i.test(`${item.name} ${item.voiceURI}`)) ??
    voices.find((item) => /zh-CN/i.test(item.lang)) ??
    voices.find((item) => /^zh/i.test(item.lang))
  if (voice) utter.voice = voice
  synth.cancel()
  synth.speak(utter)
}

async function playAlert() {
  const el = getAudio()
  playGeneration += 1
  el.muted = false
  el.volume = 1
  try {
    el.currentTime = 0
    await el.play()
  } catch {
    speakPhrase()
  }
}

/** Call from a click handler so the browser treats it as a user gesture. */
function unlockFromGesture() {
  const el = getAudio()
  const generation = ++playGeneration
  el.muted = false
  el.volume = 1
  const pending = el.play()
  void pending
    .then(() => {
      markUnlocked()
      window.setTimeout(() => {
        if (playGeneration !== generation) return
        el.pause()
        try {
          el.currentTime = 0
        } catch {
          // The element can reject a seek before metadata is ready.
        }
      }, 80)
    })
    .catch(() => {
      speakPhrase()
      markUnlocked()
    })
}

function requestNotificationPermission() {
  if (typeof Notification === 'undefined' || Notification.permission !== 'default') return
  void Notification.requestPermission().catch(() => undefined)
}

export function pressSoundToggle() {
  requestNotificationPermission()
  if (!ui.unlocked) {
    unlockFromGesture()
    if (!ui.enabled) {
      ui = { ...ui, enabled: true }
      persistEnabled()
      emitUi()
    }
    return
  }
  const enabled = !ui.enabled
  ui = { ...ui, enabled }
  persistEnabled()
  emitUi()
  if (enabled) unlockFromGesture()
}

export function previewAlertSound() {
  const el = getAudio()
  playGeneration += 1
  el.muted = false
  el.volume = 1
  try {
    el.currentTime = 0
  } catch {
    // Ignore seek failures on a not-yet-loaded clip.
  }
  const pending = el.play()
  markUnlocked()
  requestNotificationPermission()
  void pending.catch(() => {
    speakPhrase()
  })
}

function notifyDesktop(items: CaSighting[]) {
  if (typeof Notification === 'undefined' || Notification.permission !== 'granted') return
  const headline = items.length === 1 ? items[0].statusZh || '新CA' : `新CA · ${items.length} 个`
  const title = items.length === 1 ? `${headline} · ${items[0].project}` : headline
  const body = items
    .map((item) => [item.statusZh, item.provenanceZh, item.project, item.address].filter(Boolean).join('\n'))
    .join('\n\n')
    .slice(0, 500)
  try {
    new Notification(title, { body, lang: 'zh-CN', tag: 'pad-hunter-new-ca' })
  } catch {
    // Notifications can throw in a denied or insecure context.
  }
}

let reminderCount = 0
let reminderOn = true
let reminderTimer = 0

function prefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function paintTitle() {
  if (typeof document === 'undefined') return
  const base = flashing && flashOn ? `【新CA】${baseTitle}` : baseTitle
  document.title = reminderTitle(reminderCount, base, reminderOn, prefersReducedMotion())
}

function syncReminderTimer() {
  if (typeof window === 'undefined') return
  if (reminderCount <= 0 || prefersReducedMotion()) {
    window.clearInterval(reminderTimer)
    reminderTimer = 0
    reminderOn = true
    return
  }
  if (reminderTimer) return
  reminderOn = true
  reminderTimer = window.setInterval(() => {
    reminderOn = !reminderOn
    paintTitle()
  }, 1000)
}

/** Blink the tab between the page title and `(n) 新提醒` while workbench alerts are unread. */
export function setWorkbenchReminderCount(count: number) {
  const next = Number.isFinite(count) ? Math.max(0, Math.floor(count)) : 0
  if (next === reminderCount && (next === 0 || reminderTimer || prefersReducedMotion())) {
    paintTitle()
    return
  }
  reminderCount = next
  syncReminderTimer()
  paintTitle()
}

export function setBaseDocumentTitle(title: string) {
  baseTitle = title
  paintTitle()
}

function applyFlashTitle() {
  paintTitle()
}

function startTitleFlash() {
  if (typeof document === 'undefined' || !document.hidden) return
  if (flashing) {
    flashOn = true
    applyFlashTitle()
    return
  }
  flashing = true
  flashOn = true
  applyFlashTitle()
  flashTimer = window.setInterval(() => {
    flashOn = !flashOn
    applyFlashTitle()
  }, FLASH_MS)
}

function stopTitleFlash() {
  if (!flashing) return
  flashing = false
  flashOn = false
  window.clearInterval(flashTimer)
  flashTimer = 0
  paintTitle()
}

function armTitleFlash() {
  titleArmed = true
  if (typeof document !== 'undefined' && document.hidden) startTitleFlash()
}

function onVisibility() {
  if (typeof document === 'undefined') return
  if (document.hidden) {
    if (titleArmed) startTitleFlash()
    return
  }
  titleArmed = false
  stopTitleFlash()
}

export function retainWorkbenchLive(): () => void {
  workbenchLiveMounted += 1
  return () => {
    workbenchLiveMounted -= 1
  }
}

export function workbenchLiveCovering(): boolean {
  return workbenchLiveMounted > 0
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', onVisibility)
}

if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)')
  motion.addEventListener?.('change', () => {
    syncReminderTimer()
    paintTitle()
  })
}
