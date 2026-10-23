/**
 * Per-project workbench reminders (即将开始 / CA / 官网·JS).
 * Pure parsing and presentation so the socket and the check script can share them.
 * Confirmed CA copy is gated on ca_status=confirmed and alert_ok===true.
 */

import { formatShanghai } from './format'

export const WB_ALERTS_STORAGE_KEY = 'ph.wbAlerts.v1'
export const WB_ALERTS_LIMIT = 200
export const ALERT_POLL_MS = 60_000
export const ALERT_HIGHLIGHT_MS = 30_000
export const SOON_TOAST_MS = 24 * 60 * 60 * 1000
export const WORKBENCH_ALERTS_PATH = '/v1/workbench/alerts'
export const CONSOLE_LINE_LIMIT = 40

export const ALERT_UI = {
  soon: '即将开始',
  change: '官网/JS',
  delay: '延期',
  source: '来源',
  copy: '复制',
  copied: '已复制',
  fresh: '新',
  read: '已读',
  consoleTitle: '提醒控制台',
  consoleWait: '等待新提醒',
  consoleReady: '就绪',
  consoleStop: '点击停止闪烁',
  consoleCount: '条新提醒',
  confirmed: '已确认CA',
  pending: '待核验',
  nft: 'NFT 合约·不算CA',
  copycat: '疑似山寨·不算CA',
  superseded: '旧CA',
  fallbackToast: '有新的项目提醒',
} as const

export type WorkbenchAlertKind =
  | 'x_post'
  | 'site_time'
  | 'ca'
  | 'ca_signal'
  | 'js_address'
  | 'site_change'
  | 'js_change'
  | 'other'

export type WorkbenchCaStatus =
  | 'confirmed'
  | 'candidate'
  | 'suspected_copycat'
  | 'nft'
  | 'superseded'
  | 'unconfirmed'
  | ''

export interface WorkbenchAlert {
  id: string
  ts: string
  handle: string
  name: string
  kind: WorkbenchAlertKind
  summary: string
  start_at: string
  start_at_display: string
  has_clock: boolean
  tz_note: string
  is_delay: boolean
  prev_start_at: string
  address: string
  chain: string
  ca_status: WorkbenchCaStatus
  ca_status_zh: string
  alert_ok: boolean
  evidence_url: string
  quote: string
  baseline: boolean
  source: string
}

export interface CaPresentation {
  label: string
  tone: 'ok' | 'warn' | 'muted'
  confirmed: boolean
}

export type ReminderTone = 'soon' | 'ok' | 'warn' | 'muted' | 'change'

export interface ReminderView {
  key: 'soon' | 'ca' | 'change'
  id: string
  mark: '⏰' | '🪙' | '🔧'
  label: string
  body: string
  badge: CaPresentation | null
  tone: ReminderTone
  /** Non-baseline and not a 不算CA row. Still needs to be unread before it blinks. */
  urgent: boolean
  delay: boolean
  ago: string
  quote: string
  evidenceUrl: string
  address: string
  chain: string
  copyable: boolean
  ts: string
}

export interface StoredWorkbenchAlerts {
  alerts: WorkbenchAlert[]
  readIds: string[]
  unread: string[]
  seeded: boolean
}

function normalizeHandle(handle: string): string {
  return handle.replace(/^@/, '').trim()
}

function handleKey(handle: string): string {
  return normalizeHandle(handle).toLowerCase()
}

function safeHttpUrl(value: string): string {
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

const KINDS = new Set<WorkbenchAlertKind>([
  'x_post',
  'site_time',
  'ca',
  'ca_signal',
  'js_address',
  'site_change',
  'js_change',
])

const CA_STATUSES = new Set<WorkbenchCaStatus>([
  'confirmed',
  'candidate',
  'suspected_copycat',
  'nft',
  'superseded',
  'unconfirmed',
])

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function flag(value: unknown): boolean {
  return value === true
}

function timeValue(iso: string): number {
  const value = Date.parse(iso)
  return Number.isNaN(value) ? 0 : value
}

function parseKind(value: unknown): WorkbenchAlertKind {
  const text = asString(value).toLowerCase()
  if (KINDS.has(text as WorkbenchAlertKind)) return text as WorkbenchAlertKind
  return 'other'
}

function parseCaStatus(value: unknown): WorkbenchCaStatus {
  const text = asString(value).toLowerCase()
  if (CA_STATUSES.has(text as WorkbenchCaStatus)) return text as WorkbenchCaStatus
  return ''
}

function addressKey(address: string): string {
  const trimmed = address.trim()
  if (!trimmed) return ''
  if (trimmed.startsWith('0x') || trimmed.startsWith('0X')) return trimmed.toLowerCase()
  return trimmed
}

export function parseWorkbenchAlert(raw: unknown): WorkbenchAlert | null {
  const row = asRecord(raw)
  if (!row) return null
  const id = asString(row.id).slice(0, 80)
  const handle = normalizeHandle(asString(row.handle))
  if (!id || !handle) return null
  return {
    id,
    ts: asString(row.ts).slice(0, 80),
    handle,
    name: asString(row.name).slice(0, 200),
    kind: parseKind(row.kind),
    summary: asString(row.summary).slice(0, 800),
    start_at: asString(row.start_at ?? row.startAt).slice(0, 80),
    start_at_display: asString(row.start_at_display ?? row.startAtDisplay).slice(0, 80),
    has_clock: flag(row.has_clock ?? row.hasClock),
    tz_note: asString(row.tz_note ?? row.tzNote).slice(0, 40),
    is_delay: flag(row.is_delay ?? row.isDelay),
    prev_start_at: asString(row.prev_start_at ?? row.prevStartAt).slice(0, 80),
    address: asString(row.address).slice(0, 200),
    chain: asString(row.chain).slice(0, 80),
    ca_status: parseCaStatus(row.ca_status ?? row.caStatus),
    ca_status_zh: asString(row.ca_status_zh ?? row.caStatusZh).slice(0, 80),
    alert_ok: flag(row.alert_ok ?? row.alertOk),
    evidence_url: safeHttpUrl(asString(row.evidence_url ?? row.evidenceUrl)),
    quote: asString(row.quote).slice(0, 800),
    baseline: flag(row.baseline),
    source: asString(row.source).slice(0, 120),
  }
}

export function parseWorkbenchAlertList(data: unknown): WorkbenchAlert[] {
  const row = asRecord(data)
  const list = Array.isArray(data)
    ? data
    : Array.isArray(row?.alerts)
      ? row.alerts
      : Array.isArray(row?.items)
        ? row.items
        : []
  const alerts: WorkbenchAlert[] = []
  for (const entry of list) {
    const alert = parseWorkbenchAlert(entry)
    if (alert) alerts.push(alert)
  }
  return alerts
}

/** GET body, or a hello envelope. Snapshot order is newest `ts` first, capped at 200. */
export function parseWorkbenchAlertsPayload(data: unknown): WorkbenchAlert[] {
  const row = asRecord(data)
  if (!row) return normalizeAlertList(parseWorkbenchAlertList(data))
  const state = asRecord(row.state)
  if (state && (Array.isArray(state.items) || Array.isArray(state.alerts))) {
    return normalizeAlertList(parseWorkbenchAlertList(state))
  }
  return normalizeAlertList(parseWorkbenchAlertList(row))
}

export function normalizeAlertList(alerts: readonly WorkbenchAlert[]): WorkbenchAlert[] {
  const sorted = [...alerts].sort((a, b) => timeValue(b.ts) - timeValue(a.ts) || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
  const seen = new Set<string>()
  const out: WorkbenchAlert[] = []
  for (const alert of sorted) {
    if (!alert.id || seen.has(alert.id)) continue
    seen.add(alert.id)
    out.push(alert)
    if (out.length >= WB_ALERTS_LIMIT) break
  }
  return out
}

export function mergeAlertIncremental(
  current: readonly WorkbenchAlert[],
  incoming: readonly WorkbenchAlert[],
): { alerts: WorkbenchAlert[]; added: WorkbenchAlert[] } {
  const seen = new Set(current.map((alert) => alert.id))
  const added: WorkbenchAlert[] = []
  for (const alert of incoming) {
    if (!alert.id || seen.has(alert.id)) continue
    seen.add(alert.id)
    added.push(alert)
  }
  return { alerts: [...added, ...current].slice(0, WB_ALERTS_LIMIT), added }
}

export function applyParsedAlertEvent(
  current: readonly WorkbenchAlert[],
  event: { kind: string; alerts?: readonly WorkbenchAlert[] },
): WorkbenchAlert[] {
  if (event.kind === 'alerts_snapshot') return normalizeAlertList(event.alerts ?? [])
  if (event.kind === 'alerts_incremental') return mergeAlertIncremental(current, event.alerts ?? []).alerts
  return [...current]
}

export function stripLeadName(summary: string): string {
  return summary.replace(/^【[^】]*】\s*/, '').trim()
}

export function formatAlertAgo(iso: string, now = Date.now()): string {
  const time = Date.parse(iso)
  if (!iso || Number.isNaN(time)) return ''
  const seconds = Math.max(0, Math.round((now - time) / 1000))
  if (seconds < 60) return '刚刚'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours} 小时前`
  const days = Math.round(hours / 24)
  return `${days} 天前`
}

export function soonWithin24h(startAt: string, now: number): boolean {
  if (!startAt) return false
  const start = Date.parse(startAt)
  if (Number.isNaN(start)) return false
  const delta = start - now
  return delta >= 0 && delta <= SOON_TOAST_MS
}

/** Green 「已确认CA」. Toast also requires kind=ca, so a signal cannot announce a confirmed CA. */
export function isConfirmedCa(alert: Pick<WorkbenchAlert, 'ca_status' | 'alert_ok'>): boolean {
  return alert.ca_status === 'confirmed' && alert.alert_ok === true
}

/** Baseline stays quiet. NFT and copycat stay muted and never blink as a confirmed CA. */
export function reminderCanFlash(alert: Pick<WorkbenchAlert, 'baseline' | 'ca_status'>): boolean {
  if (alert.baseline) return false
  if (alert.ca_status === 'nft' || alert.ca_status === 'suspected_copycat') return false
  return true
}

function lineTone(key: ReminderView['key'], badge: CaPresentation | null): ReminderTone {
  if (key === 'soon') return 'soon'
  if (key === 'change') return 'change'
  if (badge?.tone === 'ok') return 'ok'
  if (badge?.tone === 'warn') return 'warn'
  return 'muted'
}

export function presentCa(alert: WorkbenchAlert): CaPresentation {
  if (isConfirmedCa(alert)) {
    return { label: ALERT_UI.confirmed, tone: 'ok', confirmed: true }
  }
  if (alert.ca_status === 'nft') return { label: ALERT_UI.nft, tone: 'muted', confirmed: false }
  if (alert.ca_status === 'suspected_copycat') return { label: ALERT_UI.copycat, tone: 'muted', confirmed: false }
  if (alert.ca_status === 'superseded') return { label: ALERT_UI.superseded, tone: 'muted', confirmed: false }
  return { label: ALERT_UI.pending, tone: 'warn', confirmed: false }
}

export function shouldToastAlert(alert: WorkbenchAlert, now: number): boolean {
  if (alert.baseline) return false
  if ((alert.kind === 'x_post' || alert.kind === 'site_time') && soonWithin24h(alert.start_at, now)) return true
  if (alert.kind === 'ca' && isConfirmedCa(alert)) return true
  return false
}

/** Baseline rows stay quiet. Anything else marks the project unread and highlights it for 30s. */
export function planFreshAlert(alert: WorkbenchAlert, now: number): { unread: boolean; highlightUntil: number; toast: boolean } {
  if (alert.baseline) return { unread: false, highlightUntil: 0, toast: false }
  return {
    unread: true,
    highlightUntil: now + ALERT_HIGHLIGHT_MS,
    toast: shouldToastAlert(alert, now),
  }
}

export function toastSummary(alert: WorkbenchAlert): string {
  return alert.summary.trim() || ALERT_UI.fallbackToast
}

export function remindersAllowed(input: { pinned: boolean; launched: boolean }): boolean {
  return input.pinned && !input.launched
}

export function workbenchRowDomId(handle: string): string {
  const key = handleKey(handle)
  return key ? `wb-row-${key}` : ''
}

function newest(alerts: readonly WorkbenchAlert[]): WorkbenchAlert | null {
  let best: WorkbenchAlert | null = null
  let bestTs = -Infinity
  let bestIndex = Infinity
  alerts.forEach((alert, index) => {
    const ts = timeValue(alert.ts)
    if (!best || ts > bestTs || (ts === bestTs && index < bestIndex)) {
      best = alert
      bestTs = ts
      bestIndex = index
    }
  })
  return best
}

export function pickSoon(alerts: readonly WorkbenchAlert[]): WorkbenchAlert | null {
  return newest(alerts.filter((alert) => alert.kind === 'x_post' || alert.kind === 'site_time'))
}

export function pickChange(alerts: readonly WorkbenchAlert[]): WorkbenchAlert | null {
  return newest(alerts.filter((alert) => alert.kind === 'site_change' || alert.kind === 'js_change'))
}

/**
 * Latest kind=ca. The same address keeps only its newest status, then the newest
 * of those wins. ca_signal / js_address are used only when there is no kind=ca.
 */
export function pickCa(alerts: readonly WorkbenchAlert[]): WorkbenchAlert | null {
  const cas = alerts.filter((alert) => alert.kind === 'ca')
  if (cas.length > 0) {
    const ordered = [...cas].sort((a, b) => timeValue(b.ts) - timeValue(a.ts))
    const latestByAddress = new Map<string, WorkbenchAlert>()
    for (const alert of ordered) {
      const key = addressKey(alert.address) || `\0${alert.id}`
      if (!latestByAddress.has(key)) latestByAddress.set(key, alert)
    }
    return newest([...latestByAddress.values()])
  }
  return newest(alerts.filter((alert) => alert.kind === 'ca_signal' || alert.kind === 'js_address'))
}

function soonBody(alert: WorkbenchAlert): string {
  const summary = stripLeadName(alert.summary)
  const when = alert.start_at_display.trim()
  if (when && summary && !summary.includes(when)) return `${summary} ${when}`
  return summary || when || ALERT_UI.soon
}

function changeBody(alert: WorkbenchAlert): string {
  const summary = stripLeadName(alert.summary)
  if (summary) return summary
  return alert.kind === 'js_change' ? '页面脚本有变动' : '官网有变动'
}

function viewFrom(key: ReminderView['key'], alert: WorkbenchAlert, now: number): ReminderView {
  const ca = key === 'ca'
  const badge = ca ? presentCa(alert) : null
  const confirmed = badge?.confirmed === true
  return {
    key,
    id: alert.id,
    mark: key === 'soon' ? '⏰' : key === 'ca' ? '🪙' : '🔧',
    label: key === 'soon' ? ALERT_UI.soon : key === 'change' ? ALERT_UI.change : '',
    body: key === 'soon' ? soonBody(alert) : key === 'change' ? changeBody(alert) : '',
    badge,
    tone: lineTone(key, badge),
    urgent: reminderCanFlash(alert),
    delay: key === 'soon' && alert.is_delay === true,
    ago: formatAlertAgo(alert.ts, now),
    quote: alert.quote,
    evidenceUrl: alert.evidence_url,
    address: ca ? alert.address : '',
    chain: ca ? alert.chain : '',
    copyable: confirmed && Boolean(alert.address),
    ts: alert.ts,
  }
}

export function reminderViews(alerts: readonly WorkbenchAlert[], now: number): ReminderView[] {
  const views: ReminderView[] = []
  const soon = pickSoon(alerts)
  const ca = pickCa(alerts)
  const change = pickChange(alerts)
  if (soon) views.push(viewFrom('soon', soon, now))
  if (ca) views.push(viewFrom('ca', ca, now))
  if (change) views.push(viewFrom('change', change, now))
  return views
}

/** User-visible reminder copy, including address, chain, quote, and the source link. */
export function reminderVisibleText(views: readonly ReminderView[]): string {
  return views
    .map((view) =>
      [
        view.mark,
        view.label,
        view.body,
        view.badge?.label ?? '',
        view.delay ? ALERT_UI.delay : '',
        view.ago,
        view.address,
        view.chain,
        view.quote,
        view.evidenceUrl,
        view.evidenceUrl ? ALERT_UI.source : '',
        view.copyable ? ALERT_UI.copy : '',
      ]
        .filter(Boolean)
        .join(' '),
    )
    .join('\n')
}

export function alertsByHandle(alerts: readonly WorkbenchAlert[]): Map<string, WorkbenchAlert[]> {
  const map = new Map<string, WorkbenchAlert[]>()
  for (const alert of alerts) {
    const key = handleKey(alert.handle)
    if (!key) continue
    const list = map.get(key)
    if (list) list.push(alert)
    else map.set(key, [alert])
  }
  return map
}

export function alertsForHandle(alerts: readonly WorkbenchAlert[], handle: string): WorkbenchAlert[] {
  const key = handleKey(handle)
  if (!key) return []
  return alerts.filter((alert) => handleKey(alert.handle) === key)
}

const READ_ID_LIMIT = 500
const TONE_RANK: ReminderTone[] = ['soon', 'ok', 'warn', 'change', 'muted']

function cleanReadIds(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  const ids: string[] = []
  const seen = new Set<string>()
  for (const entry of value) {
    const id = asString(entry)
    if (!id || seen.has(id)) continue
    seen.add(id)
    ids.push(id)
  }
  return ids.slice(-READ_ID_LIMIT)
}

export function loadStoredWorkbenchAlerts(raw: string | null): StoredWorkbenchAlerts {
  const empty: StoredWorkbenchAlerts = { alerts: [], readIds: [], unread: [], seeded: false }
  if (!raw) return empty
  try {
    const parsed: unknown = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      const alerts = normalizeAlertList(parseWorkbenchAlertList(parsed))
      return { alerts, readIds: alerts.map((alert) => alert.id), unread: [], seeded: true }
    }
    const row = asRecord(parsed)
    if (!row) return empty
    const alerts = parseWorkbenchAlertsPayload(row.alerts ?? row)
    const unread = Array.isArray(row.unread)
      ? [...new Set(row.unread.map((entry) => handleKey(asString(entry))).filter(Boolean))]
      : []
    let readIds: string[]
    if (Array.isArray(row.readIds)) readIds = cleanReadIds(row.readIds)
    else if (unread.length > 0) {
      const pending = new Set(unread)
      readIds = alerts.filter((alert) => !pending.has(handleKey(alert.handle))).map((alert) => alert.id)
    } else readIds = alerts.map((alert) => alert.id)
    return { alerts, readIds, unread, seeded: true }
  } catch {
    return empty
  }
}

export interface ConsoleLine {
  id: string
  handle: string
  name: string
  ts: string
  stamp: string
  mark: '⏰' | '🪙' | '🔧' | '·'
  label: string
  text: string
  tone: ReminderTone
  flash: boolean
}

function consoleParts(alert: WorkbenchAlert): Pick<ConsoleLine, 'mark' | 'label' | 'text' | 'tone'> {
  if (alert.kind === 'x_post' || alert.kind === 'site_time') {
    const body = soonBody(alert)
    return {
      mark: '⏰',
      label: ALERT_UI.soon,
      tone: 'soon',
      text: alert.is_delay ? `${ALERT_UI.delay} ${body}` : body,
    }
  }
  if (alert.kind === 'site_change' || alert.kind === 'js_change') {
    return { mark: '🔧', label: ALERT_UI.change, tone: 'change', text: changeBody(alert) }
  }
  if (alert.kind === 'ca' || alert.kind === 'ca_signal' || alert.kind === 'js_address') {
    const badge = presentCa(alert)
    const tone: ReminderTone = badge.tone === 'ok' ? 'ok' : badge.tone === 'warn' ? 'warn' : 'muted'
    return {
      mark: '🪙',
      label: badge.label,
      tone,
      text: [alert.address, alert.chain].filter(Boolean).join(' '),
    }
  }
  return {
    mark: '·',
    label: '其他',
    tone: 'muted',
    text: stripLeadName(alert.summary) || ALERT_UI.fallbackToast,
  }
}

function passesVisibility(
  alert: WorkbenchAlert,
  visible?: { pinned?: ReadonlySet<string>; launched?: ReadonlySet<string>; handle?: string },
): boolean {
  const key = handleKey(alert.handle)
  if (!key) return false
  if (visible?.handle && handleKey(visible.handle) !== key) return false
  if (!visible?.pinned) return true
  return visible.pinned.has(key) && !visible.launched?.has(key)
}

/** Unread, non-baseline alerts that are allowed to blink. 不算CA and baseline stay out. */
export function flashingAlertIds(
  alerts: readonly WorkbenchAlert[],
  readIds: ReadonlySet<string>,
  visible?: { pinned?: ReadonlySet<string>; launched?: ReadonlySet<string>; handle?: string },
): string[] {
  const ids: string[] = []
  for (const alert of alerts) {
    if (!alert.id || readIds.has(alert.id) || !reminderCanFlash(alert)) continue
    if (!passesVisibility(alert, visible)) continue
    ids.push(alert.id)
  }
  return ids
}

/** How many alerts are still blinking. Launched and unpinned projects are skipped when a filter is passed. */
export function flashingReminderCount(
  alerts: readonly WorkbenchAlert[],
  readIds: ReadonlySet<string>,
  visible?: { pinned?: ReadonlySet<string>; launched?: ReadonlySet<string>; handle?: string },
): number {
  return flashingAlertIds(alerts, readIds, visible).length
}

/**
 * Command-line log. Newest unread lines stay at the top so a new blink is in view.
 * Quiet history follows, capped so the panel stays a window.
 */
export function consoleLines(
  alerts: readonly WorkbenchAlert[],
  readIds: ReadonlySet<string>,
  visible?: { pinned?: ReadonlySet<string>; launched?: ReadonlySet<string>; handle?: string },
): ConsoleLine[] {
  const ranked = alerts.map((alert, index) => ({ alert, index })).filter(({ alert }) => passesVisibility(alert, visible))
  ranked.sort((a, b) => {
    const delta = timeValue(b.alert.ts) - timeValue(a.alert.ts)
    if (delta !== 0) return delta
    return a.index - b.index
  })
  const flashing: ConsoleLine[] = []
  const quiet: ConsoleLine[] = []
  for (const { alert } of ranked) {
    const parts = consoleParts(alert)
    const line: ConsoleLine = {
      id: alert.id,
      handle: alert.handle,
      name: alert.name,
      ts: alert.ts,
      stamp: formatShanghai(alert.ts),
      ...parts,
      flash: Boolean(alert.id) && reminderCanFlash(alert) && !readIds.has(alert.id),
    }
    if (line.flash) flashing.push(line)
    else quiet.push(line)
  }
  return [...flashing, ...quiet].slice(0, CONSOLE_LINE_LIMIT)
}

export function consoleVisibleText(lines: readonly ConsoleLine[]): string {
  return lines.map((line) => [line.stamp, line.mark, line.label, line.text].filter(Boolean).join(' ')).join('\n')
}

/** Border color for a row. A blinking line wins over a quiet one, and 即将开始 wins over the other tones. */
export function rowAttentionTone(views: readonly ReminderView[], readIds: ReadonlySet<string>): ReminderTone | null {
  if (views.length === 0) return null
  const flashing = views.filter((view) => view.urgent && view.id && !readIds.has(view.id))
  const pool = flashing.length > 0 ? flashing : views
  for (const tone of TONE_RANK) {
    if (pool.some((view) => view.tone === tone)) return tone
  }
  return pool[0]?.tone ?? null
}

/** Tab title while unread reminders are waiting. Reduced motion keeps the count beside the normal title. */
export function reminderTitle(count: number, base: string, blinkOn: boolean, reduceMotion = false): string {
  if (count <= 0) return base
  const badge = `(${count}) 新提醒`
  if (reduceMotion) return `${badge} · ${base}`
  return blinkOn ? badge : base
}
