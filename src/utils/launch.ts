import type { Candidate, MonitorEvent } from '../types'
import { snapshotForCandidate, type MonitorSnapshot } from './monitor'
import { isAlreadyOpened } from './opening'

/** Today through the Shanghai day three days ahead, inclusive. */
const WINDOW_DAYS = 3

const LAUNCH_HINT = /开盘|上线|发射|开铸|启动|tge|\b(?:listing|launch|mint|live)\b/i
const ISO_RE = /(\d{4})-(\d{2})-(\d{2})(?:[T\s](\d{2}):(\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:?\d{2})?)?/g
const CN_RE = /(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*日(?:\s*(\d{1,2})\s*[:：点时]\s*(\d{1,2}))?/g

const RELATIVE: { re: RegExp; addDays: number }[] = [
  { re: /大后天(?:\s*(\d{1,2})\s*[:：点时]\s*(\d{1,2}))?/g, addDays: 3 },
  { re: /(?<!大)后天(?:\s*(\d{1,2})\s*[:：点时]\s*(\d{1,2}))?/g, addDays: 2 },
  { re: /今晚(?:\s*(\d{1,2})\s*[:：点时]\s*(\d{1,2}))?/g, addDays: 0 },
  { re: /(?:明天|明日)(?:\s*(\d{1,2})\s*[:：点时]\s*(\d{1,2}))?/g, addDays: 1 },
  { re: /(?:今天|今日)(?:\s*(\d{1,2})\s*[:：点时]\s*(\d{1,2}))?/g, addDays: 0 },
]

export interface ListingTimeEntry {
  handle: string
  listing_at: string
  listing_at_source?: string
}

export interface ResolvedLaunch {
  at: string
  dateOnly: boolean
  source?: string
}

export interface UpcomingRow {
  candidate: Candidate
  launch: ResolvedLaunch
  snap: MonitorSnapshot
}

interface FoundDate {
  at: Date
  dateOnly: boolean
  absolute: boolean
}

function pad(value: number): string {
  return String(value).padStart(2, '0')
}

function shanghaiYmd(date: Date): { year: number; month: number; day: number } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date)
  const get = (type: string) => Number(parts.find((part) => part.type === type)?.value)
  return { year: get('year'), month: get('month'), day: get('day') }
}

export function shanghaiDayStart(date: Date): Date {
  const { year, month, day } = shanghaiYmd(date)
  return new Date(`${year}-${pad(month)}-${pad(day)}T00:00:00+08:00`)
}

function shanghaiDateTime(year: number, month: number, day: number, hour = 0, minute = 0): Date | null {
  if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) return null
  const iso = `${year}-${pad(month)}-${pad(day)}T${pad(hour)}:${pad(minute)}:00+08:00`
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return null
  const ymd = shanghaiYmd(date)
  if (ymd.year !== year || ymd.month !== month || ymd.day !== day) return null
  return date
}

export function upcomingWindow(now = new Date()): { start: Date; end: Date } {
  const start = shanghaiDayStart(now)
  const end = new Date(start.getTime() + (WINDOW_DAYS + 1) * 24 * 60 * 60 * 1000)
  return { start, end }
}

export function isInUpcomingWindow(iso: string, now = new Date()): boolean {
  const time = Date.parse(iso)
  if (Number.isNaN(time)) return false
  const { start, end } = upcomingWindow(now)
  return time >= start.getTime() && time < end.getTime()
}

export function normalizeListingSource(value?: string | null): string | undefined {
  const text = value?.trim() ?? ''
  if (!text) return undefined
  const lower = text.toLowerCase()
  if (lower === 'site' || lower === 'web' || lower === 'website' || text.includes('站点') || text.includes('网站')) return 'site'
  if (lower === 'x' || lower === 'twitter' || text.includes('推特')) return 'x'
  if (lower === 'tg' || lower === 'telegram' || lower.includes('telegram') || text.includes('电报')) return 'tg'
  return text
}

export function listingSourceLabel(source?: string): string {
  if (source === 'site') return '站点'
  if (source === 'x') return 'X'
  if (source === 'tg') return 'TG 卡片'
  return source ?? ''
}

export function formatLaunchLabel(launch: ResolvedLaunch): string {
  const date = new Date(launch.at)
  if (Number.isNaN(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    month: 'numeric',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  const label = `${Number(get('month'))}月${Number(get('day'))}日`
  if (launch.dateOnly) return label
  return `${label} ${get('hour')}:${get('minute')}`
}

function parseIsoField(value?: string | null): { at: string; dateOnly: boolean } | null {
  const text = value?.trim() ?? ''
  if (!text) return null
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(text)
  const normalized = dateOnly ? `${text}T00:00:00+08:00` : text
  const time = Date.parse(normalized)
  if (Number.isNaN(time)) return null
  return { at: new Date(time).toISOString(), dateOnly }
}

export function structuredLaunch(candidate: Pick<Candidate, 'listing_at' | 'launch_at' | 'listing_at_source'>): ResolvedLaunch | null {
  const parsed = parseIsoField(candidate.listing_at) ?? parseIsoField(candidate.launch_at)
  if (!parsed) return null
  return { ...parsed, source: normalizeListingSource(candidate.listing_at_source) }
}

function candidateChannel(candidate: Candidate): string | undefined {
  const source = candidate.source?.toLowerCase() ?? ''
  if (source.includes('telegram') || source.includes('tg')) return 'tg'
  if (source.includes('twitter') || source === 'x') return 'x'
  return undefined
}

function signalChannel(text: string): string {
  return /(?:^|[;\n；])\s*(?:listing|status)\s*[=：]/i.test(text) ? 'site' : 'x'
}

function findDates(text: string, now: Date): FoundDate[] {
  const found: FoundDate[] = []
  const { year } = shanghaiYmd(now)
  const today = shanghaiDayStart(now)

  ISO_RE.lastIndex = 0
  for (const match of text.matchAll(ISO_RE)) {
    const [, y, m, d, hh, mm, , zone] = match
    const hasTime = Boolean(hh)
    if (!hasTime && !zone) {
      const date = shanghaiDateTime(Number(y), Number(m), Number(d))
      if (date) found.push({ at: date, dateOnly: true, absolute: true })
      continue
    }
    const raw = zone || hasTime ? match[0] : ''
    const stamped = zone ? raw : `${y}-${m}-${d}T${hh}:${mm}:00+08:00`
    const time = Date.parse(stamped)
    if (!Number.isNaN(time)) found.push({ at: new Date(time), dateOnly: false, absolute: true })
  }

  CN_RE.lastIndex = 0
  for (const match of text.matchAll(CN_RE)) {
    const hasYear = Boolean(match[1])
    const hasTime = match[4] != null
    const month = Number(match[2])
    const day = Number(match[3])
    const hour = hasTime ? Number(match[4]) : 0
    const minute = hasTime ? Number(match[5] ?? 0) : 0
    let date = shanghaiDateTime(hasYear ? Number(match[1]) : year, month, day, hour, minute)
    if (!date) continue
    if (!hasYear && date.getTime() < today.getTime()) {
      date = shanghaiDateTime(year + 1, month, day, hour, minute)
    }
    if (date) found.push({ at: date, dateOnly: !hasTime, absolute: true })
  }

  for (const { re, addDays } of RELATIVE) {
    re.lastIndex = 0
    for (const match of text.matchAll(re)) {
      const hasTime = match[1] != null
      const base = new Date(today.getTime() + addDays * 24 * 60 * 60 * 1000)
      const ymd = shanghaiYmd(base)
      const date = shanghaiDateTime(
        ymd.year,
        ymd.month,
        ymd.day,
        hasTime ? Number(match[1]) : 0,
        hasTime ? Number(match[2] ?? 0) : 0,
      )
      if (date) found.push({ at: date, dateOnly: !hasTime, absolute: false })
    }
  }

  return found
}

function pickLaunchDate(found: FoundDate[], now: Date): { at: Date; dateOnly: boolean } | null {
  if (found.length === 0) return null
  const { start, end } = upcomingWindow(now)
  const inWindow = found.filter((item) => item.at.getTime() >= start.getTime() && item.at.getTime() < end.getTime())
  const pool = inWindow.length > 0 ? inWindow : found.filter((item) => item.absolute)
  if (pool.length === 0) return null
  const absolute = pool.filter((item) => item.absolute)
  const choices = (absolute.length > 0 ? absolute : pool).slice().sort((a, b) => a.at.getTime() - b.at.getTime())
  return choices[0] ?? null
}

function launchFromText(text: string | null | undefined, now: Date, requireHint: boolean): { at: string; dateOnly: boolean } | null {
  const raw = text?.trim() ?? ''
  if (!raw) return null
  if (requireHint && !LAUNCH_HINT.test(raw)) return null
  const picked = pickLaunchDate(findDates(raw, now), now)
  if (!picked) return null
  return { at: picked.at.toISOString(), dateOnly: picked.dateOnly }
}

export function resolveLaunch(
  candidate: Candidate,
  snap: MonitorSnapshot,
  overlays: ReadonlyMap<string, ListingTimeEntry>,
  now = new Date(),
): ResolvedLaunch | null {
  const structured = structuredLaunch(candidate)
  if (structured) return structured

  const overlay = overlays.get(candidate.handle.replace(/^@/, '').trim().toLowerCase())
  const overlayParsed = overlay ? parseIsoField(overlay.listing_at) : null
  if (overlayParsed) {
    return { ...overlayParsed, source: normalizeListingSource(overlay?.listing_at_source) }
  }

  const channel = candidateChannel(candidate)
  const attempts: { text?: string | null; source?: string; requireHint: boolean }[] = [
    { text: candidate.listing, source: channel, requireHint: false },
    { text: candidate.why, source: channel, requireHint: true },
    { text: candidate.listing_signal, source: candidate.listing_signal ? signalChannel(candidate.listing_signal) : undefined, requireHint: true },
    { text: snap.lastSignal?.text, source: snap.lastSignal?.text ? signalChannel(snap.lastSignal.text) : undefined, requireHint: true },
  ]
  for (const attempt of attempts) {
    const parsed = launchFromText(attempt.text, now, attempt.requireHint)
    if (parsed && isInUpcomingWindow(parsed.at, now)) return { ...parsed, source: attempt.source }
  }

  return null
}

export function indexListingTimes(entries: ListingTimeEntry[]): Map<string, ListingTimeEntry> {
  const map = new Map<string, ListingTimeEntry>()
  for (const entry of entries) {
    const handle = entry.handle.replace(/^@/, '').trim().toLowerCase()
    if (!handle || map.has(handle)) continue
    map.set(handle, entry)
  }
  return map
}

export function upcomingLaunches(
  candidates: Candidate[],
  events: MonitorEvent[],
  times: ListingTimeEntry[] = [],
  now = new Date(),
): UpcomingRow[] {
  const overlays = indexListingTimes(times)
  const rows: UpcomingRow[] = []
  for (const candidate of candidates) {
    const snap = snapshotForCandidate(candidate, events)
    if (isAlreadyOpened(candidate, snap)) continue
    const launch = resolveLaunch(candidate, snap, overlays, now)
    if (!launch || !isInUpcomingWindow(launch.at, now)) continue
    rows.push({ candidate, launch, snap })
  }
  rows.sort(
    (a, b) =>
      Date.parse(a.launch.at) - Date.parse(b.launch.at) ||
      a.candidate.name.localeCompare(b.candidate.name, 'zh'),
  )
  return rows
}

export function countUpcoming(
  candidates: Candidate[],
  events: MonitorEvent[],
  times: ListingTimeEntry[] = [],
  now = new Date(),
): number {
  return upcomingLaunches(candidates, events, times, now).length
}

export function readListingTimes(data: unknown): ListingTimeEntry[] {
  if (!data || typeof data !== 'object') return []
  const times = (data as { times?: unknown }).times
  if (!Array.isArray(times)) return []
  const entries: ListingTimeEntry[] = []
  for (const row of times) {
    if (!row || typeof row !== 'object') continue
    const record = row as Record<string, unknown>
    const handle = typeof record.handle === 'string' ? record.handle.trim() : ''
    const listingAt = typeof record.listing_at === 'string' ? record.listing_at.trim() : ''
    if (!handle || !listingAt) continue
    const source = typeof record.listing_at_source === 'string' ? record.listing_at_source : undefined
    entries.push({ handle, listing_at: listingAt, listing_at_source: source })
  }
  return entries
}
