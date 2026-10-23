/**
 * 推送日期: when a project first entered the radar from the TG push monitor.
 *
 * The published candidates do not have a dedicated column. The frontend takes the
 * earliest real timestamp among these fields (snake_case or camelCase):
 *
 * 1. `push_date` — canonical value `scripts/telegram/sync_site.py` now writes
 * 2. `first_seen`
 * 3. `added_at`
 * 4. `synced_at`
 * 5. `created_at`
 * 6. `date_iso` — Telegram message time of the push card (what the current JSON has)
 *
 * Launch and probe times are not entry times and are never used:
 * `listing_at`, `launch_at`, `fetched_at`, `last_checked`, `detected_at`,
 * `removed_at`, `completion_updated_at`, `x_progress_at`.
 * Missing or unparseable values stay 未知. Nothing is invented.
 */

export const PUSH_DATE_FIELDS = [
  'push_date',
  'first_seen',
  'added_at',
  'synced_at',
  'created_at',
  'date_iso',
] as const

export type PushDateField = (typeof PUSH_DATE_FIELDS)[number]

export const UNKNOWN_PUSH_DATE = '未知'

export interface PushStamp {
  /** ISO-8601 instant. Date-only values are Shanghai midnight. */
  at: string
  dateOnly: boolean
  field: PushDateField
}

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/
const UNIX_SECONDS = /^\d{10}$/
const UNIX_MILLIS = /^\d{13}$/
const EMPTY = /^(未知|unknown|null|none|n\/a|—|-)$/i
const MIN_MS = Date.UTC(2015, 0, 1)
const MAX_MS = Date.UTC(2100, 0, 1)

function camelCase(key: string): string {
  return key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())
}

function readField(record: unknown, key: string): unknown {
  if (!record || typeof record !== 'object') return undefined
  const obj = record as Record<string, unknown>
  if (key in obj && obj[key] != null) return obj[key]
  const camel = camelCase(key)
  if (camel in obj && obj[camel] != null) return obj[camel]
  return undefined
}

function fromMillis(ms: number, dateOnly: boolean, at?: string): { ms: number; at: string; dateOnly: boolean } | null {
  if (!Number.isFinite(ms) || ms < MIN_MS || ms > MAX_MS) return null
  return { ms, at: at ?? new Date(ms).toISOString(), dateOnly }
}

function parseValue(value: unknown): { ms: number; at: string; dateOnly: boolean } | null {
  if (typeof value === 'number') {
    if (!Number.isFinite(value) || value <= 0) return null
    const ms = value < 1e12 ? value * 1000 : value
    return fromMillis(ms, false)
  }
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text || EMPTY.test(text)) return null
  if (UNIX_SECONDS.test(text) || UNIX_MILLIS.test(text)) {
    const raw = Number(text)
    const ms = text.length === 10 ? raw * 1000 : raw
    return fromMillis(ms, false)
  }
  const dateOnly = DATE_ONLY.exec(text)
  if (dateOnly) {
    const at = `${text}T00:00:00+08:00`
    const ms = Date.parse(at)
    return fromMillis(ms, true, at)
  }
  const ms = Date.parse(text)
  return fromMillis(ms, false, text)
}

/** Earliest usable entry timestamp across the given records. */
export function resolvePushDate(records: readonly unknown[]): PushStamp | null {
  let bestMs = Number.POSITIVE_INFINITY
  let bestPriority: number = PUSH_DATE_FIELDS.length
  let best: PushStamp | null = null
  for (const record of records) {
    if (!record || typeof record !== 'object') continue
    for (let priority = 0; priority < PUSH_DATE_FIELDS.length; priority += 1) {
      const field = PUSH_DATE_FIELDS[priority]
      const parsed = parseValue(readField(record, field))
      if (!parsed) continue
      if (parsed.ms < bestMs || (parsed.ms === bestMs && priority < bestPriority)) {
        bestMs = parsed.ms
        bestPriority = priority
        best = { at: parsed.at, dateOnly: parsed.dateOnly, field }
      }
    }
  }
  return best
}

/** Asia/Shanghai `YYYY-MM-DD` or `YYYY-MM-DD HH:mm`. Empty when the stamp is missing. */
export function formatPushDate(stamp: PushStamp | null | undefined): string {
  if (!stamp) return ''
  if (stamp.dateOnly) {
    const dated = stamp.at.match(/^(\d{4}-\d{2}-\d{2})/)
    if (dated) return dated[1]
  }
  const date = new Date(stamp.at)
  if (Number.isNaN(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  const hour = get('hour') === '24' ? '00' : get('hour')
  return `${get('year')}-${get('month')}-${get('day')} ${hour}:${get('minute')}`
}

export function pushDateText(records: readonly unknown[]): string {
  return formatPushDate(resolvePushDate(records)) || UNKNOWN_PUSH_DATE
}

/** Milliseconds of the displayed 推送日期. `0` when the card has no push date. */
export function pushDateMillis(records: readonly unknown[]): number {
  const stamp = resolvePushDate(records)
  if (!stamp) return 0
  const ms = Date.parse(stamp.at)
  return Number.isFinite(ms) ? ms : 0
}

function handleKey(record: unknown): string {
  if (!record || typeof record !== 'object') return ''
  const obj = record as Record<string, unknown>
  const raw = obj.handle ?? obj.twitter_handle ?? obj.twitterHandle ?? ''
  return String(raw).replace(/^@/, '').trim().toLowerCase()
}

function stampMillis(stamp: PushStamp): number {
  const ms = Date.parse(stamp.at)
  return Number.isNaN(ms) ? Number.POSITIVE_INFINITY : ms
}

/** Rows from `projects.json`: a list, or `{ projects | candidates: [] }`. */
export function projectRows(data: unknown): unknown[] {
  if (Array.isArray(data)) return data
  if (!data || typeof data !== 'object') return []
  const obj = data as Record<string, unknown>
  if (Array.isArray(obj.projects)) return obj.projects
  if (Array.isArray(obj.candidates)) return obj.candidates
  return []
}

/**
 * Earliest project-snapshot row per handle.
 * Used when a candidate was restored without `date_iso` but the TG snapshot still has one.
 */
export function indexProjectPush(data: unknown): Map<string, unknown> {
  const index = new Map<string, unknown>()
  for (const row of projectRows(data)) {
    const handle = handleKey(row)
    if (!handle) continue
    const prev = index.get(handle)
    if (!prev) {
      index.set(handle, row)
      continue
    }
    const prevStamp = resolvePushDate([prev])
    const nextStamp = resolvePushDate([row])
    if (nextStamp && (!prevStamp || stampMillis(nextStamp) < stampMillis(prevStamp))) index.set(handle, row)
  }
  return index
}

/**
 * Copy a real snapshot timestamp onto `push_date` when the candidate itself has none.
 * Does not set `date_iso` or `listing_at`, so launch sorting and launch gates stay as they are.
 */
export function withProjectPushDates<T extends { handle?: string }>(candidates: T[], projects: unknown): T[] {
  const index = indexProjectPush(projects)
  if (index.size === 0) return candidates
  return candidates.map((candidate) => {
    if (resolvePushDate([candidate])) return candidate
    const row = index.get(handleKey(candidate))
    const stamp = resolvePushDate(row ? [row] : [])
    if (!stamp) return candidate
    return { ...candidate, push_date: stamp.at }
  })
}
