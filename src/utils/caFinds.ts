import type { CaFind, CaFindConfidence, CaFindSource, CaFindsPayload } from '../types'

export const CA_FINDS_URL = `${import.meta.env.BASE_URL}data/ca_finds.json`

export const CA_SOURCE_LABEL: Record<CaFindSource, string> = {
  site: 'site',
  js: 'JS',
  x: 'X',
  tg: 'TG',
  'on-chain': 'on-chain',
}

const SOURCE_ALIASES: Record<string, CaFindSource> = {
  site: 'site',
  website: 'site',
  web: 'site',
  站点: 'site',
  js: 'js',
  javascript: 'js',
  script: 'js',
  x: 'x',
  twitter: 'x',
  tweet: 'x',
  tg: 'tg',
  telegram: 'tg',
  'on-chain': 'on-chain',
  onchain: 'on-chain',
  'on chain': 'on-chain',
  chain: 'on-chain',
  链上: 'on-chain',
}

export const LOW_CONFIDENCE_HINT =
  '低置信：例如 Baola、Ballast 等信息流站点上的第三方代币图标，不一定是项目自己公布的合约。'

interface Explorer {
  label: string
  href: (address: string) => string
}

const EXPLORERS: Record<string, Explorer> = {
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
  scroll: { label: 'Scrollscan', href: (address) => `https://scrollscan.com/address/${address}` },
  linea: { label: 'Lineascan', href: (address) => `https://lineascan.build/address/${address}` },
  zksync: { label: 'zkSync Explorer', href: (address) => `https://explorer.zksync.io/address/${address}` },
  mantle: { label: 'Mantlescan', href: (address) => `https://mantlescan.xyz/address/${address}` },
  fantom: { label: 'FTMScan', href: (address) => `https://ftmscan.com/address/${address}` },
  gnosis: { label: 'Gnosisscan', href: (address) => `https://gnosisscan.io/address/${address}` },
  celo: { label: 'Celoscan', href: (address) => `https://celoscan.io/address/${address}` },
  hyperevm: { label: 'HyperEVMScan', href: (address) => `https://hyperevmscan.io/address/${address}` },
  sui: { label: 'Suiscan', href: (address) => `https://suiscan.xyz/mainnet/account/${address}` },
  ton: { label: 'Tonviewer', href: (address) => `https://tonviewer.com/${address}` },
  aptos: { label: 'Aptos Explorer', href: (address) => `https://explorer.aptoslabs.com/account/${address}?network=mainnet` },
  sei: { label: 'Seitrace', href: (address) => `https://seitrace.com/address/${address}` },
  sonic: { label: 'SonicScan', href: (address) => `https://sonicscan.org/address/${address}` },
  berachain: { label: 'Berascan', href: (address) => `https://berascan.com/address/${address}` },
  abstract: { label: 'Abscan', href: (address) => `https://abscan.org/address/${address}` },
  worldchain: { label: 'Worldscan', href: (address) => `https://worldscan.org/address/${address}` },
  unichain: { label: 'Uniscan', href: (address) => `https://uniscan.xyz/address/${address}` },
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
  'binance smart chain': 'bsc',
  polygon: 'polygon',
  matic: 'polygon',
  pol: 'polygon',
  arb: 'arbitrum',
  arbitrum: 'arbitrum',
  'arbitrum one': 'arbitrum',
  op: 'optimism',
  optimism: 'optimism',
  avax: 'avalanche',
  avalanche: 'avalanche',
  tron: 'tron',
  trx: 'tron',
  blast: 'blast',
  scroll: 'scroll',
  linea: 'linea',
  zksync: 'zksync',
  'zksync era': 'zksync',
  mantle: 'mantle',
  fantom: 'fantom',
  ftm: 'fantom',
  gnosis: 'gnosis',
  xdai: 'gnosis',
  celo: 'celo',
  hyperevm: 'hyperevm',
  hyperliquid: 'hyperevm',
  'hyper evm': 'hyperevm',
  sui: 'sui',
  ton: 'ton',
  aptos: 'aptos',
  apt: 'aptos',
  sei: 'sei',
  sonic: 'sonic',
  berachain: 'berachain',
  bera: 'berachain',
  abstract: 'abstract',
  worldchain: 'worldchain',
  'world chain': 'worldchain',
  unichain: 'unichain',
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

export function normalizeCaSource(value: string): string {
  const key = value.trim().toLowerCase()
  return SOURCE_ALIASES[key] ?? value.trim()
}

export function caSourceLabel(source: string): string {
  if (source in CA_SOURCE_LABEL) return CA_SOURCE_LABEL[source as CaFindSource]
  return source || '未知来源'
}

export function normalizeCaConfidence(value: string): CaFindConfidence | '' {
  const key = value.trim().toLowerCase()
  if (key === 'high' || key === 'h' || key === '高' || key === '高置信') return 'high'
  if (key === 'low' || key === 'l' || key === '低' || key === '低置信') return 'low'
  return ''
}

export function detectedMs(find: CaFind): number {
  const time = Date.parse(find.detected_at)
  return Number.isNaN(time) ? 0 : time
}

function addressIdentity(address: string): string {
  const trimmed = address.trim()
  if (trimmed.startsWith('0x') || trimmed.startsWith('0X')) return trimmed.toLowerCase()
  return trimmed
}

/** Stable identity for "appeared since page load". Checksum-only changes do not count as new. */
export function caFindKey(find: CaFind): string {
  return [
    find.handle.replace(/^@/, '').trim().toLowerCase(),
    find.project.trim().toLowerCase(),
    find.chain.trim().toLowerCase(),
    addressIdentity(find.address),
    find.source.trim().toLowerCase(),
    find.detected_at.trim(),
    find.evidence_url.trim(),
  ].join('\n')
}

export function projectGroupKey(find: CaFind): string {
  const handle = find.handle.replace(/^@/, '').trim().toLowerCase()
  if (handle) return `h:${handle}`
  const project = find.project.trim().toLowerCase()
  if (project) return `p:${project}`
  return `a:${addressIdentity(find.address)}`
}

export function parseCaFinds(data: unknown): CaFindsPayload {
  if (!data || typeof data !== 'object') throw new Error('无效的 JSON')
  const obj = data as Record<string, unknown>
  if (!Array.isArray(obj.finds)) throw new Error('JSON 需包含 finds 数组')
  const finds: CaFind[] = []
  const seen = new Set<string>()
  for (const item of obj.finds) {
    if (!item || typeof item !== 'object') continue
    const row = item as Record<string, unknown>
    const address = asString(row.address)
    if (!address) continue
    const find: CaFind = {
      project: asString(row.project),
      handle: asString(row.handle).replace(/^@/, ''),
      chain: asString(row.chain),
      address,
      source: normalizeCaSource(asString(row.source)),
      evidence_url: asString(row.evidence_url),
      detected_at: asString(row.detected_at),
      confidence: normalizeCaConfidence(asString(row.confidence)),
      note: asString(row.note),
    }
    const key = caFindKey(find)
    if (seen.has(key)) continue
    seen.add(key)
    finds.push(find)
  }
  finds.sort((a, b) => detectedMs(b) - detectedMs(a) || a.address.localeCompare(b.address))
  return {
    generated_at: typeof obj.generated_at === 'string' ? obj.generated_at : undefined,
    finds,
  }
}

export interface CaFindFilters {
  search: string
  chain: string
  confidence: 'all' | CaFindConfidence
}

export function filterCaFinds(finds: CaFind[], filters: CaFindFilters): CaFind[] {
  const query = filters.search.trim().toLowerCase().replace(/^@/, '')
  return finds.filter((find) => {
    if (filters.chain && find.chain !== filters.chain) return false
    if (filters.confidence !== 'all' && find.confidence !== filters.confidence) return false
    if (!query) return true
    const hay = `${find.project} ${find.handle} ${find.address}`.toLowerCase()
    return hay.includes(query)
  })
}

export function chainOptions(finds: CaFind[]): string[] {
  return [...new Set(finds.map((find) => find.chain).filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh'))
}

export interface CaProjectGroup {
  key: string
  project: string
  handle: string
  finds: CaFind[]
}

export function groupCaFinds(finds: CaFind[]): CaProjectGroup[] {
  const groups = new Map<string, CaProjectGroup>()
  for (const find of finds) {
    const key = projectGroupKey(find)
    let group = groups.get(key)
    if (!group) {
      group = {
        key,
        project: find.project,
        handle: find.handle,
        finds: [],
      }
      groups.set(key, group)
    }
    if (!group.project && find.project) group.project = find.project
    if (!group.handle && find.handle) group.handle = find.handle
    group.finds.push(find)
  }
  return [...groups.values()]
}

export function explorerFor(chain: string, address: string): { label: string; url: string } | null {
  const key = CHAIN_ALIASES[chain.trim().toLowerCase().replace(/\s+/g, ' ')]
  const explorer = key ? EXPLORERS[key] : undefined
  if (!explorer || !address.trim()) return null
  return { label: explorer.label, url: explorer.href(encodeURIComponent(address.trim())) }
}

export function safeEvidenceUrl(value: string): string | null {
  try {
    const url = new URL(value)
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
    return url.toString()
  } catch {
    return null
  }
}
