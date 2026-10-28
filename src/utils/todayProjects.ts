/** Projects auto-enrolled with a concrete listing time inside the next 48 hours. */

export interface TodayProjectSource {
  label: string
  url: string
}

export interface TodayProjectPlaybook {
  updated_at?: string
  summary?: string
  玩法: string[]
  参与需求: string[]
  步骤: string[]
  风险注意: string[]
  来源: TodayProjectSource[]
}

export interface TodayProject {
  handle: string
  name: string
  chain: string
  site?: string
  tweet_url?: string
  listing_at?: string
  listing_at_display?: string
  hours_to_launch?: number
  status?: string
  playbook?: TodayProjectPlaybook
}

export interface TodayProjectsDocument {
  generated_at?: string
  timezone?: string
  count: number
  items: TodayProject[]
}

export const EMPTY_TODAY_PROJECTS: TodayProjectsDocument = { count: 0, items: [] }

const PLAYBOOK_LISTS = ['玩法', '参与需求', '步骤', '风险注意'] as const

export type TodayPlaybookListKey = (typeof PLAYBOOK_LISTS)[number]

function text(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function httpUrl(value: unknown): string | undefined {
  const url = text(value)
  if (!/^https?:\/\//i.test(url)) return undefined
  return url
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => text(item)).filter(Boolean)
}

function readSources(value: unknown): TodayProjectSource[] {
  if (!Array.isArray(value)) return []
  const sources: TodayProjectSource[] = []
  for (const item of value) {
    if (!item || typeof item !== 'object') continue
    const row = item as Record<string, unknown>
    const url = httpUrl(row.url)
    if (!url) continue
    sources.push({ label: text(row.label) || url, url })
  }
  return sources
}

function readPlaybook(value: unknown): TodayProjectPlaybook | undefined {
  if (!value || typeof value !== 'object') return undefined
  const row = value as Record<string, unknown>
  const playbook: TodayProjectPlaybook = {
    updated_at: text(row.updated_at) || undefined,
    summary: text(row.summary) || undefined,
    玩法: stringList(row['玩法']),
    参与需求: stringList(row['参与需求']),
    步骤: stringList(row['步骤']),
    风险注意: stringList(row['风险注意']),
    来源: readSources(row['来源']),
  }
  const hasBody =
    Boolean(playbook.summary) ||
    playbook.来源.length > 0 ||
    PLAYBOOK_LISTS.some((key) => playbook[key].length > 0)
  return hasBody ? playbook : undefined
}

function readItem(value: unknown): TodayProject | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const handle = text(row.handle).replace(/^@+/, '')
  const name = text(row.name)
  if (!handle && !name) return null
  const listingAt = text(row.listing_at)
  const listingDisplay = text(row.listing_at_display)
  const hours = typeof row.hours_to_launch === 'number' && Number.isFinite(row.hours_to_launch) ? row.hours_to_launch : undefined
  return {
    handle,
    name: name || handle,
    chain: text(row.chain),
    site: httpUrl(row.site),
    tweet_url: httpUrl(row.tweet_url),
    listing_at: listingAt || undefined,
    listing_at_display: listingDisplay || undefined,
    hours_to_launch: hours,
    status: text(row.status) || undefined,
    playbook: readPlaybook(row.playbook),
  }
}

/** Soonest `listing_at` first. Rows without a parseable instant stay in place at the end. */
export function sortTodayProjects(items: readonly TodayProject[]): TodayProject[] {
  return items.map((item, index) => ({ item, index })).sort((a, b) => {
    const left = listingInstant(a.item.listing_at)
    const right = listingInstant(b.item.listing_at)
    const leftOk = left != null
    const rightOk = right != null
    if (leftOk && rightOk && left !== right) return left - right
    if (leftOk !== rightOk) return leftOk ? -1 : 1
    return a.index - b.index
  }).map((entry) => entry.item)
}

export function listingInstant(value?: string): number | null {
  if (!value) return null
  const time = Date.parse(value)
  return Number.isNaN(time) ? null : time
}

export function readTodayProjects(data: unknown): TodayProjectsDocument {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return EMPTY_TODAY_PROJECTS
  const row = data as Record<string, unknown>
  const items = sortTodayProjects(
    (Array.isArray(row.items) ? row.items : []).flatMap((item) => {
      const parsed = readItem(item)
      return parsed ? [parsed] : []
    }),
  )
  const count = typeof row.count === 'number' && Number.isFinite(row.count) ? Math.max(0, Math.trunc(row.count)) : items.length
  return {
    generated_at: text(row.generated_at) || undefined,
    timezone: text(row.timezone) || undefined,
    count,
    items,
  }
}

/** Missing file and `count === 0` both produce an empty list, so the section stays hidden. */
export function todayProjectsToShow(doc: TodayProjectsDocument | null | undefined): TodayProject[] {
  if (!doc || doc.count <= 0 || doc.items.length === 0) return []
  return sortTodayProjects(doc.items)
}

export function countdownLabel(listingAt: string | undefined, now: Date): string | null {
  const time = listingInstant(listingAt)
  if (time == null) return null
  const ms = time - now.getTime()
  if (ms <= 0) return '已到点'
  const totalSeconds = Math.floor(ms / 1000)
  const days = Math.floor(totalSeconds / 86400)
  const hours = Math.floor((totalSeconds % 86400) / 3600)
  const minutes = Math.floor((totalSeconds % 3600) / 60)
  const seconds = totalSeconds % 60
  if (days > 0) return `${days}天${hours}小时${minutes}分`
  if (hours > 0) return `${hours}小时${minutes}分`
  if (minutes > 0) return `${minutes}分${seconds}秒`
  return `${seconds}秒`
}

export function hoursToLaunchLabel(hours: number | undefined): string | null {
  if (typeof hours !== 'number' || !Number.isFinite(hours)) return null
  const rounded = Math.round(hours * 10) / 10
  const textValue = Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1)
  return `${textValue} 小时`
}

export interface TodayTimeView {
  primary: string
  secondary: string
  dateTime?: string
  kind: 'countdown' | 'display' | 'hours'
}

/** Clock text comes only from `listing_at`, `listing_at_display`, or `hours_to_launch`. */
export function todayTimeView(item: TodayProject, now: Date): TodayTimeView | null {
  const display = item.listing_at_display?.trim() ?? ''
  const countdown = countdownLabel(item.listing_at, now)
  if (countdown) {
    return {
      primary: countdown,
      secondary: display && display !== countdown ? display : '',
      dateTime: item.listing_at,
      kind: 'countdown',
    }
  }
  if (display) {
    return { primary: display, secondary: '', kind: 'display' }
  }
  const hours = hoursToLaunchLabel(item.hours_to_launch)
  if (!hours) return null
  return { primary: hours, secondary: '', kind: 'hours' }
}

export function playbookGroups(playbook: TodayProjectPlaybook | undefined): Array<{ label: TodayPlaybookListKey; lines: string[] }> {
  if (!playbook) return []
  return PLAYBOOK_LISTS.flatMap((label) => {
    const lines = playbook[label]
    return lines.length > 0 ? [{ label, lines }] : []
  })
}
