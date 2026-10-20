import type { Candidate, MonitorEvent } from '../types'
import { snapshotForCandidate, type MonitorSnapshot } from './monitor'

const HOT_STATUS = new Set(['mint进行中', '即将启动', '今日开盘'])
const HOT_LISTING = new Set(['今日开盘', '即将开盘'])

/** Phrases that mean the project is already open / listed / trading. */
const OPENED_CN = ['已开盘', '已上线', '已上市', '开盘中', '交易中', '正在交易'] as const

const FIELD_PATTERN = /(?:^|[;\n；])\s*(listing|status)\s*[=：]\s*([^;\n；]+)/gi

export interface OpeningReason {
  id: 'today' | 'mint' | 'soon' | 'listing' | 'signal'
  label: string
  weight: number
}

function shanghaiDate(now: Date): { year: string; month: string; day: string } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(now)
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  return { year: get('year'), month: get('month'), day: get('day') }
}

export function mentionsToday(text: string | null | undefined, now = new Date()): boolean {
  if (!text) return false
  const { year, month, day } = shanghaiDate(now)
  const monthNum = String(Number(month))
  const dayNum = String(Number(day))
  const needles = [`${year}-${month}-${day}`, `${year}/${month}/${day}`, `${monthNum}月${dayNum}日`, `${month}月${day}日`]
  return needles.some((needle) => text.includes(needle))
}

function fieldSaysOpened(value: string | null | undefined): boolean {
  const text = value?.trim() ?? ''
  if (!text) return false
  if (OPENED_CN.some((phrase) => text.includes(phrase))) return true
  if (/^(live|trading|listed)$/i.test(text)) return true
  if (/\b(?:now|already|currently)\s+listed\b/i.test(text)) return true
  return englishSaysOpened(text)
}

/** Short status fields match `live` / `trading`. Longer blurbs only match a clear "already live" phrase. */
function englishSaysOpened(text: string): boolean {
  const live = /\blive\b/i.test(text)
  const trading = /\btrading\b/i.test(text)
  if (!live && !trading) return false
  const pendingLive =
    /\b(?:not|pre|before|going|upcoming)\b[\s-]*live\b/i.test(text) ||
    /\blive\s+soon\b/i.test(text) ||
    /\bwill\s+be\s+live\b/i.test(text) ||
    /\byet\s+to\s+(?:go\s+)?live\b/i.test(text)
  const definitelyLive = /\b(?:now|already|currently|went)\s+live\b/i.test(text)
  const liveOpened = live && (!pendingLive || definitelyLive)
  const tradingOpened = trading && !/\b(?:not|pre|before)\b[\s-]*trading\b/i.test(text)
  if (text.length > 48 && !definitelyLive && !/\b(?:now|started|already)\s+trading\b/i.test(text)) {
    return false
  }
  return liveOpened || tradingOpened
}

function signalSaysOpened(text: string | null | undefined): boolean {
  const raw = text?.trim() ?? ''
  if (!raw) return false
  const fields: string[] = []
  for (const match of raw.matchAll(new RegExp(FIELD_PATTERN.source, 'gi'))) {
    const value = match[2]?.trim()
    if (value) fields.push(value)
  }
  if (fields.length > 0) return fields.some((field) => fieldSaysOpened(field))
  return fieldSaysOpened(raw)
}

/** True when the candidate or the latest monitor listing says the project is already open. */
export function isAlreadyOpened(candidate: Candidate, snap: MonitorSnapshot): boolean {
  if (fieldSaysOpened(candidate.listing) || fieldSaysOpened(candidate.status)) return true
  if (signalSaysOpened(snap.lastSignal?.text) || signalSaysOpened(candidate.listing_signal)) return true
  return false
}

export function openingReasons(candidate: Candidate, snap: MonitorSnapshot, now = new Date()): OpeningReason[] {
  if (isAlreadyOpened(candidate, snap)) return []
  const reasons: OpeningReason[] = []
  const listing = candidate.listing?.trim() || ''
  const status = candidate.status?.trim() || ''
  const dated = [listing, candidate.why, candidate.listing_signal, snap.lastSignal?.text].some((text) =>
    mentionsToday(text, now),
  )
  if (dated || listing.includes('今日') || HOT_LISTING.has(listing)) {
    const label = listing === '即将开盘' ? listing : '今日开盘'
    reasons.push({ id: 'today', label, weight: 0 })
  }
  if (status === 'mint进行中') reasons.push({ id: 'mint', label: 'mint进行中', weight: 1 })
  else if (status === '即将启动') reasons.push({ id: 'soon', label: '即将启动', weight: 2 })
  else if (HOT_STATUS.has(status)) reasons.push({ id: 'listing', label: status, weight: 2 })
  if (snap.lastSignal?.text || candidate.listing_signal) {
    reasons.push({ id: 'signal', label: '开盘信号', weight: 3 })
  }
  return reasons
}

export function openingWeight(reasons: OpeningReason[]): number {
  if (reasons.length === 0) return 99
  return Math.min(...reasons.map((reason) => reason.weight))
}

export function countToday(candidates: Candidate[], events: MonitorEvent[]): number {
  return candidates.filter((candidate) => openingReasons(candidate, snapshotForCandidate(candidate, events)).length > 0)
    .length
}
