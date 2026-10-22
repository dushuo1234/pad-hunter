import type { Candidate } from '../types'
import { launchTimeText, structuredLaunch } from './launch'

export interface LaunchedItem {
  project: string
  handle: string
  chain: string
  category: string
  xUrl: string
  sites: string[]
  listingAt: string | null
  ca: string | null
  caChain: string | null
  reason: string
  evidence: string
  removedAt: string
  /** Entry timestamps for 推送日期. Launch time stays on `listingAt`. */
  push_date?: string
  first_seen?: string
  added_at?: string
  synced_at?: string
  created_at?: string
  date_iso?: string
}

export interface LaunchedDocument {
  generatedAt?: string
  count: number
  items: LaunchedItem[]
}

export function normalizeHandle(handle: string | null | undefined): string {
  return (handle ?? '').replace(/^@/, '').trim().toLowerCase()
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asNullable(value: unknown): string | null {
  if (value == null) return null
  const text = asString(value)
  return text || null
}

const PUSH_KEYS = ['push_date', 'first_seen', 'added_at', 'synced_at', 'created_at', 'date_iso'] as const

function pushFields(item: Record<string, unknown>): Partial<Pick<LaunchedItem, (typeof PUSH_KEYS)[number]>> {
  const out: Partial<Pick<LaunchedItem, (typeof PUSH_KEYS)[number]>> = {}
  for (const key of PUSH_KEYS) {
    const camel = key.replace(/_([a-z])/g, (_, letter: string) => letter.toUpperCase())
    const value = item[key] ?? item[camel]
    if (typeof value === 'number' && Number.isFinite(value)) {
      out[key] = String(value)
      continue
    }
    const text = asString(value)
    if (text) out[key] = text
  }
  return out
}

export function readLaunched(data: unknown): LaunchedDocument {
  if (!data || typeof data !== 'object') return { count: 0, items: [] }
  const record = data as Record<string, unknown>
  const rawItems = Array.isArray(record.items) ? record.items : []
  const items: LaunchedItem[] = []
  for (const row of rawItems) {
    if (!row || typeof row !== 'object') continue
    const item = row as Record<string, unknown>
    const sites = Array.isArray(item.sites) ? item.sites.map(asString).filter(Boolean) : []
    items.push({
      project: asString(item.project),
      handle: asString(item.handle).replace(/^@/, ''),
      chain: asString(item.chain),
      category: asString(item.category),
      xUrl: asString(item.x_url || item.xUrl),
      sites,
      listingAt: asNullable(item.listing_at ?? item.listingAt),
      ca: asNullable(item.ca),
      caChain: asNullable(item.ca_chain ?? item.caChain),
      reason: asString(item.reason),
      evidence: asString(item.evidence),
      removedAt: asString(item.removed_at || item.removedAt),
      ...pushFields(item),
    })
  }
  items.sort((a, b) => (Date.parse(b.removedAt) || 0) - (Date.parse(a.removedAt) || 0))
  const generatedAt = asString(record.generated_at || record.generatedAt) || undefined
  return { generatedAt, count: items.length, items }
}

export function launchedHandleSet(items: LaunchedItem[]): Set<string> {
  const set = new Set<string>()
  for (const item of items) {
    const handle = normalizeHandle(item.handle)
    if (handle) set.add(handle)
  }
  return set
}

export function isLaunchedHandle(handles: Set<string>, handle: string | null | undefined): boolean {
  const key = normalizeHandle(handle)
  return key !== '' && handles.has(key)
}

export function withoutLaunched(candidates: Candidate[], handles: Set<string>): Candidate[] {
  if (handles.size === 0) return candidates
  return candidates.filter((candidate) => !isLaunchedHandle(handles, candidate.handle))
}

export function launchLabel(listingAt: string | null): string {
  return launchTimeText(structuredLaunch({ listing_at: listingAt }))
}

export function formatRemovedAt(iso: string | null | undefined): string {
  if (!iso) return '未知'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '未知'
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
  return `${get('year')}-${get('month')}-${get('day')} ${get('hour')}:${get('minute')}`
}

export function explorerUrl(ca: string, chain?: string | null): string | null {
  const addr = ca.trim()
  if (!addr) return null
  const key = (chain ?? '').toLowerCase()
  if (/ethereum|\beth\b|erc/.test(key)) return `https://etherscan.io/token/${addr}`
  if (/bsc|bnb|binance/.test(key)) return `https://bscscan.com/token/${addr}`
  if (/\bbase\b/.test(key)) return `https://basescan.org/token/${addr}`
  if (/arbitrum|\barb\b/.test(key)) return `https://arbiscan.io/token/${addr}`
  if (/optimism|\bop\b/.test(key)) return `https://optimistic.etherscan.io/token/${addr}`
  if (/polygon|matic/.test(key)) return `https://polygonscan.com/token/${addr}`
  if (/avalanche|avax/.test(key)) return `https://snowtrace.io/token/${addr}`
  if (/solana|\bsol\b/.test(key)) return `https://solscan.io/token/${addr}`
  if (/tron|\btrx\b/.test(key)) return `https://tronscan.org/#/token20/${addr}`
  return null
}
