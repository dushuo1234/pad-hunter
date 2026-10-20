import type { Candidate } from '../types'
import { findByHandle } from './candidates'
import type { LaunchedIndex, WorkbenchStatusItem } from './workbenchApi'
import { isLaunched, sitesForPin } from './workbenchApi'
import type { WorkbenchItem } from './workbench'

export type PillTone = 'ok' | 'bad' | 'warn' | 'muted'

export interface LaunchBadge {
  label: '已上线' | '未上线' | '未知'
  tone: PillTone
}

export interface SiteBadge {
  label: string
  tone: PillTone
  title: string
}

const EXPLORERS: Record<string, { label: string; href: (address: string) => string }> = {
  ethereum: { label: 'Etherscan', href: (address) => `https://etherscan.io/address/${address}` },
  base: { label: 'Basescan', href: (address) => `https://basescan.org/address/${address}` },
  solana: { label: 'Solscan', href: (address) => `https://solscan.io/account/${address}` },
  bsc: { label: 'BscScan', href: (address) => `https://bscscan.com/address/${address}` },
  polygon: { label: 'Polygonscan', href: (address) => `https://polygonscan.com/address/${address}` },
  arbitrum: { label: 'Arbiscan', href: (address) => `https://arbiscan.io/address/${address}` },
  optimism: { label: 'Optimistic Etherscan', href: (address) => `https://optimistic.etherscan.io/address/${address}` },
  avalanche: { label: 'Snowtrace', href: (address) => `https://snowtrace.io/address/${address}` },
  tron: { label: 'Tronscan', href: (address) => `https://tronscan.org/#/address/${address}` },
  blast: { label: 'Blastscan', href: (address) => `https://blastscan.io/address/${address}` },
  sui: { label: 'Suiscan', href: (address) => `https://suiscan.xyz/mainnet/account/${address}` },
  hyperevm: { label: 'HyperEVMScan', href: (address) => `https://hyperevmscan.io/address/${address}` },
  ton: { label: 'Tonviewer', href: (address) => `https://tonviewer.com/${address}` },
  aptos: { label: 'Aptos Explorer', href: (address) => `https://explorer.aptoslabs.com/account/${address}?network=mainnet` },
}

const CHAIN_ALIASES: Record<string, string> = {
  eth: 'ethereum',
  ethereum: 'ethereum',
  erc20: 'ethereum',
  'erc-20': 'ethereum',
  以太坊: 'ethereum',
  base: 'base',
  sol: 'solana',
  solana: 'solana',
  bsc: 'bsc',
  bnb: 'bsc',
  binance: 'bsc',
  'bnb chain': 'bsc',
  polygon: 'polygon',
  matic: 'polygon',
  arb: 'arbitrum',
  arbitrum: 'arbitrum',
  op: 'optimism',
  optimism: 'optimism',
  avax: 'avalanche',
  avalanche: 'avalanche',
  tron: 'tron',
  trx: 'tron',
  blast: 'blast',
  sui: 'sui',
  hyperevm: 'hyperevm',
  hyperliquid: 'hyperevm',
  'hyper evm': 'hyperevm',
  ton: 'ton',
  aptos: 'aptos',
  apt: 'aptos',
}

export function formatAgo(iso: string, now = Date.now()): string {
  const time = Date.parse(iso)
  if (!iso || Number.isNaN(time)) return ''
  const seconds = Math.max(0, Math.round((now - time) / 1000))
  if (seconds < 60) return `${seconds}秒前`
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}分钟前`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours}小时前`
  const days = Math.round(hours / 24)
  return `${days}天前`
}

export function formatInterval(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds <= 0) return ''
  if (seconds < 60) return `${Math.round(seconds)}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}分钟`
  const hours = seconds / 3600
  return `${hours >= 10 ? Math.round(hours) : hours.toFixed(1).replace(/\.0$/, '')}小时`
}

export function formatMs(ms: number | null): string {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return ''
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(ms >= 10000 ? 0 : 1).replace(/\.0$/, '')}s`
}

export function formatBytes(bytes: number | null): string {
  if (bytes == null || !Number.isFinite(bytes) || bytes < 0) return ''
  if (bytes < 1024) return `${Math.round(bytes)}B`
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))}KB`
  return `${(bytes / 1024 / 1024).toFixed(1).replace(/\.0$/, '')}MB`
}

export function formatShanghaiFull(iso?: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  const hour = get('hour')
  return `${get('year')}/${get('month')}/${get('day')} ${hour === '24' ? '00' : hour}:${get('minute')}:${get('second')}`
}

export function formatListingAt(value: string): string {
  const text = value.trim()
  if (!text || text === '未知' || text.toLowerCase() === 'unknown') return '未知'
  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(text)
  const parsed = new Date(dateOnly ? `${text}T00:00:00+08:00` : text)
  if (Number.isNaN(parsed.getTime())) return text
  return formatShanghaiFull(parsed.toISOString()).replace(/:\d{2}$/, '')
}

export function listingSourceLabel(source: string): string {
  const text = source.trim()
  const lower = text.toLowerCase()
  if (!text) return ''
  if (lower === 'site' || lower === 'web' || lower === 'website' || text.includes('站点') || text.includes('网站')) return '站点'
  if (lower === 'x' || lower === 'twitter' || text.includes('推特')) return 'X'
  if (lower === 'tg' || lower === 'telegram' || text.includes('电报')) return 'TG'
  return text
}

export function projectLaunch(status: WorkbenchStatusItem | undefined, now = Date.now()): LaunchBadge {
  if (!status) return { label: '未知', tone: 'muted' }
  if (status.alreadyListed) return { label: '已上线', tone: 'ok' }
  if (status.listingAt && status.listingAt !== '未知') {
    const time = Date.parse(status.listingAt)
    if (!Number.isNaN(time)) return time <= now ? { label: '已上线', tone: 'ok' } : { label: '未上线', tone: 'muted' }
  }
  return { label: '未上线', tone: 'muted' }
}

export function siteBadge(status: WorkbenchStatusItem | undefined, checking: boolean): SiteBadge {
  if (!status && !checking) return { label: '未知', tone: 'muted', title: '' }
  if (checking || status?.checking) {
    return { label: '检查中', tone: 'warn', title: status?.lastError || '正在检查' }
  }
  if (!status || status.siteStatus === 'unknown') {
    return { label: '未知', tone: 'muted', title: status?.lastError || (status?.polled ? '' : '尚未检查') }
  }
  const http = Number(status.httpCode)
  if (status.siteStatus === 'up' && Number.isFinite(http) && http >= 400) {
    return { label: '危险中', tone: 'warn', title: status.lastError || `HTTP ${status.httpCode}` }
  }
  if (status.siteStatus === 'up') {
    return { label: '已上线', tone: 'ok', title: [status.httpCode ? `HTTP ${status.httpCode}` : '', status.lastError].filter(Boolean).join(' · ') }
  }
  return { label: '未上线', tone: 'bad', title: status.lastError || (status.httpCode ? `HTTP ${status.httpCode}` : '') }
}

export function displayUrl(item: WorkbenchItem, candidate: Candidate | undefined, status: WorkbenchStatusItem | undefined): string {
  if (status?.url) return status.url
  return sitesForPin(item, candidate)[0] ?? ''
}

export function urlProtocol(url: string): string {
  if (url.startsWith('https://')) return 'https'
  if (url.startsWith('http://')) return 'http'
  return ''
}

export function hostLabel(url: string): string {
  if (!url) return ''
  try {
    const parsed = new URL(url)
    const path = parsed.pathname === '/' ? '' : parsed.pathname
    return `${parsed.host}${path}${parsed.search}`.replace(/\/$/, '')
  } catch {
    return url.replace(/^https?:\/\//, '')
  }
}

export function introFor(candidate: Candidate | undefined): string {
  const text = candidate?.why?.trim() || candidate?.bio?.trim() || ''
  return text
}

export function chainLabel(item: WorkbenchItem, candidate: Candidate | undefined): string {
  return candidate?.chain?.trim() || item.caChain.trim()
}

export function rowLaunched(index: LaunchedIndex, item: WorkbenchItem): boolean {
  return isLaunched(index, item)
}

export function candidateFor(item: WorkbenchItem, candidates: Candidate[]): Candidate | undefined {
  return item.handle ? findByHandle(candidates, item.handle) : undefined
}

export function explorerFor(chain: string, address: string): { label: string; url: string } | null {
  const trimmed = address.trim()
  if (!trimmed) return null
  const alias = CHAIN_ALIASES[chain.trim().toLowerCase().replace(/\s+/g, ' ')]
  const inferred = alias || inferChain(trimmed)
  const explorer = inferred ? EXPLORERS[inferred] : undefined
  if (!explorer) return null
  return { label: explorer.label, url: explorer.href(encodeURIComponent(trimmed)) }
}

function inferChain(address: string): string | null {
  if (/^0x[a-fA-F0-9]{40}$/.test(address)) return 'ethereum'
  if (/^[1-9A-HJ-NP-Za-km-z]{32,44}$/.test(address)) return 'solana'
  return null
}

export function summaryText(online: number | null, offline: number | null, total: number, contracts: number | null): string {
  const up = online == null ? '—' : String(online)
  const down = offline == null ? '—' : String(offline)
  const found = contracts == null ? '—' : String(contracts)
  return `共 ${total} 个目标 · 已上线 ${up} · 未上线 ${down} · 合约总数 ${found}`
}

export function countSummary(rows: Array<WorkbenchStatusItem | undefined>, hasStatus: boolean): {
  online: number | null
  offline: number | null
  contracts: number | null
} {
  if (!hasStatus) return { online: null, offline: null, contracts: null }
  let online = 0
  let contracts = 0
  for (const status of rows) {
    if (status?.siteStatus === 'up') online += 1
    contracts += status?.addressCount ?? 0
  }
  return { online, offline: rows.length - online, contracts }
}
