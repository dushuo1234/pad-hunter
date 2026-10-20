import type { Candidate, MonitorEvent } from '../types'
import { snapshotForCandidate, type MonitorSnapshot } from './monitor'

const HOT_STATUS = new Set(['mint进行中', '即将启动', '今日开盘', '开盘中', '已开盘'])
const HOT_LISTING = new Set(['今日开盘', '已开盘', '即将开盘', '开盘中'])

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

export function openingReasons(candidate: Candidate, snap: MonitorSnapshot, now = new Date()): OpeningReason[] {
  const reasons: OpeningReason[] = []
  const listing = candidate.listing?.trim() || ''
  const status = candidate.status?.trim() || ''
  const dated = [listing, candidate.why, candidate.listing_signal, snap.lastSignal?.text].some((text) =>
    mentionsToday(text, now),
  )
  if (dated || listing.includes('今日') || HOT_LISTING.has(listing)) {
    const label = listing === '已开盘' || listing === '开盘中' || listing === '即将开盘' ? listing : '今日开盘'
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
