import type { CaFind } from '../types'
import { caAddressId } from './caFinds'
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
}

export interface CaToast {
  id: string
  project: string
  address: string
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
  const empty: SeenState = { ids: new Set(), baselined: { ca: false, workbench: false } }
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
    return {
      ids: new Set(addresses),
      baselined: { ca: flags.ca === true, workbench: flags.workbench === true },
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
    }
    localStorage.setItem(SEEN_KEY, JSON.stringify(payload))
  } catch {
    // Keep the in-memory set so this tab does not re-alert.
  }
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
  return finds.map((find) => ({
    address: find.address,
    project: projectLabel(find.project, find.handle),
  }))
}

export function sightingsFromStatus(items: WorkbenchStatusItem[]): CaSighting[] {
  const sightings: CaSighting[] = []
  for (const item of items) {
    const project = projectLabel(item.name, item.handle)
    for (const address of item.lastAddresses) {
      sightings.push({ address, project })
    }
  }
  return sightings
}

export function sightingsFromDetail(project: string, handle: string, addresses: FoundAddress[]): CaSighting[] {
  return addresses.map((found) => ({
    address: found.address,
    project: projectLabel(found.label || project, handle),
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
    novel.push({ address: sighting.address.trim(), project: sighting.project })
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
  queueNovel(novel)
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
export function observeWorkbenchDetail(handle: string, project: string, addresses: FoundAddress[]) {
  const key = handleKey(handle) || project.trim().toLowerCase()
  const sightings = sightingsFromDetail(project, handle, addresses)
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
    address: item.address,
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

function soundUrl(): string {
  const base = import.meta.env.BASE_URL || '/'
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
  const title = items.length === 1 ? `新CA · ${items[0].project}` : `新CA · ${items.length} 个`
  const body = items.map((item) => `${item.project}\n${item.address}`).join('\n\n').slice(0, 500)
  try {
    new Notification(title, { body, lang: 'zh-CN', tag: 'pad-hunter-new-ca' })
  } catch {
    // Notifications can throw in a denied or insecure context.
  }
}

export function setBaseDocumentTitle(title: string) {
  baseTitle = title
  if (typeof document === 'undefined') return
  if (!flashing) document.title = title
  else document.title = flashOn ? `【新CA】${title}` : title
}

function applyFlashTitle() {
  document.title = flashOn ? `【新CA】${baseTitle}` : baseTitle
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
  if (typeof document !== 'undefined') document.title = baseTitle
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
