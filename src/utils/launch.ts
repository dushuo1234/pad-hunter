import type { Candidate, MonitorEvent } from '../types'
import { snapshotForCandidate, type MonitorSnapshot } from './monitor'
import { isAlreadyOpened } from './opening'
import {
  completionFacets,
  completionTags,
  isAboutToStart,
  pickScrape,
  recordFromSignalText,
} from './upcomingSignals'

/** Today through the Shanghai day three days ahead, inclusive. */
const WINDOW_DAYS = 3

export const UNKNOWN_LAUNCH = '未知'

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
  /** Null when the row is included without a confirmed listing time. Display that as 未知. */
  launch: ResolvedLaunch | null
  snap: MonitorSnapshot
  /**
   * Why an untimed row is here: 即将启动, and/or high site/JS/is-file completion
   * of the project, its contract code, or its game code. Empty for timed rows.
   */
  tags: string[]
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

export function launchTimeText(launch: ResolvedLaunch | null | undefined): string {
  if (!launch) return UNKNOWN_LAUNCH
  return formatLaunchLabel(launch) || UNKNOWN_LAUNCH
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

/** listing_at / launch_at, or the same fields from listing_times.json. Free text does not count. */
export function resolveLaunch(
  candidate: Candidate,
  overlays: ReadonlyMap<string, ListingTimeEntry>,
): ResolvedLaunch | null {
  const structured = structuredLaunch(candidate)
  if (structured) return structured

  const overlay = overlays.get(candidate.handle.replace(/^@/, '').trim().toLowerCase())
  const overlayParsed = overlay ? parseIsoField(overlay.listing_at) : null
  if (!overlayParsed) return null
  return { ...overlayParsed, source: normalizeListingSource(overlay?.listing_at_source) }
}

export function applyListingTimes(candidates: Candidate[], times: ListingTimeEntry[]): Candidate[] {
  if (times.length === 0) return candidates
  const overlays = indexListingTimes(times)
  return candidates.map((candidate) => {
    if (structuredLaunch(candidate)) return candidate
    const entry = overlays.get(candidate.handle.replace(/^@/, '').trim().toLowerCase())
    if (!entry || !parseIsoField(entry.listing_at)) return candidate
    return {
      ...candidate,
      listing_at: entry.listing_at,
      listing_at_source: entry.listing_at_source ?? candidate.listing_at_source,
    }
  })
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

function postedAt(candidate: Candidate): number {
  const time = Date.parse(candidate.date_iso || '')
  return Number.isNaN(time) ? 0 : time
}

/**
 * 即将开盘 rows.
 *
 * 1. Confirmed `listing_at` / `launch_at` inside the next 3 Shanghai days, soonest first.
 * 2. Otherwise, only when there is no resolved listing time: status or listing signal
 *    「即将启动」 (or an equivalent about-to-start phrase), or high completion of the
 *    project / contract code / game code from site, JS, or is-file scrape fields.
 *    Those show no invented time. Newest `date_iso` first, then name.
 *
 * A resolved listing time outside the window stays off this list.
 * Already-open wording and `already_listed` are excluded. Callers also drop `launched.json`.
 */
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
    if (isAlreadyOpened(candidate, snap) || candidate.already_listed === true) continue
    const launch = resolveLaunch(candidate, overlays)
    const timed = Boolean(launch && isInUpcomingWindow(launch.at, now))
    const signalText = snap.lastSignal?.text
    const starting = isAboutToStart(candidate, signalText)
    const facets = completionFacets([
      pickScrape(candidate as Candidate & Record<string, unknown>),
      recordFromSignalText(signalText),
      recordFromSignalText(candidate.listing_signal),
      snap.siteScrape,
      snap.signalScrape,
    ])
    const ready = facets.project || facets.contract || facets.game
    if (!timed && (launch || (!starting && !ready))) continue
    const tags = timed ? [] : [...(starting ? ['即将启动'] : []), ...completionTags(facets)]
    rows.push({ candidate, launch: timed ? launch : null, snap, tags })
  }
  rows.sort((a, b) => {
    if (Boolean(a.launch) !== Boolean(b.launch)) return a.launch ? -1 : 1
    if (a.launch && b.launch) {
      return (
        Date.parse(a.launch.at) - Date.parse(b.launch.at) ||
        a.candidate.name.localeCompare(b.candidate.name, 'zh')
      )
    }
    return postedAt(b.candidate) - postedAt(a.candidate) || a.candidate.name.localeCompare(b.candidate.name, 'zh')
  })
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
