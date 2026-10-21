import type {
  CaFind,
  CaFindConfidence,
  CaFindSource,
  CaFindsPayload,
  CaProjectLock,
  CaProvenance,
  CaRole,
  CaStatus,
  CaStatusCounts,
} from '../types'
import { matchLaunched, type LaunchedItem } from './launched'

const publicBase = typeof import.meta.env?.BASE_URL === 'string' ? import.meta.env.BASE_URL : '/'
export const CA_FINDS_URL = `${publicBase}data/ca_finds.json`

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

export const EMPTY_STATUS_COUNTS: CaStatusCounts = {
  confirmed: 0,
  candidate: 0,
  superseded: 0,
  not_ca: 0,
}

const STATUS_ZH: Record<Exclude<CaStatus, ''>, string> = {
  confirmed: '已确认CA',
  candidate: '待确认',
  superseded: '非正式·官推未认',
  not_ca: '非CA',
  suspected_copycat: '疑似山寨',
}

const PROVENANCE_ZH: Record<Exclude<CaProvenance, ''>, string> = {
  wallet_factory: '监控钱包创建',
  official_x: '官推确认',
  both: '监控钱包创建+官推确认',
}

export const CA_ROLE_ZH: Record<Exclude<CaRole, ''>, string> = {
  token: '代币',
  transistors: '晶体管',
  processor: 'Processor',
}

const STATUSES = new Set<string>(['confirmed', 'candidate', 'superseded', 'not_ca', 'suspected_copycat'])
const PROVENANCES = new Set<string>(['wallet_factory', 'official_x', 'both'])
const ROLES = new Set<string>(['token', 'transistors', 'processor'])

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
  if (key === 'medium' || key === 'm' || key === 'med' || key === '中' || key === '中置信') return 'medium'
  if (key === 'low' || key === 'l' || key === '低' || key === '低置信') return 'low'
  return ''
}

export function displayProjectName(project: string, handle = ''): string {
  const stripped = project.replace(/^【[^】]*】\s*/, '').trim()
  if (stripped) return stripped
  const normalized = handle.trim().replace(/^@/, '')
  if (normalized) return `@${normalized}`
  return '未命名项目'
}

/** Handle plus the project name before ·, so TapeOutWatch and TapeRobot share one lock. */
export function caProjectAliases(project: string, handle: string, projectKey = ''): string[] {
  const aliases: string[] = []
  const normalized = handle.trim().replace(/^@/, '').toLowerCase()
  if (normalized) aliases.push(`h:${normalized}`)
  const key = projectKey.trim().toLowerCase()
  if (key) aliases.push(`k:${key}`)
  const stripped = project.replace(/^【[^】]*】\s*/, '').trim().toLowerCase()
  if (stripped) {
    aliases.push(`p:${stripped}`)
    const head = stripped.split(/[·•|/]/)[0]?.trim()
    if (head) aliases.push(`n:${head}`)
  }
  return aliases
}

export function lockForFind(locks: CaProjectLock[], find: CaFind): CaProjectLock | null {
  return lockForHandle(locks, find.handle, find.project, find.projectKey)
}

export function lockForHandle(locks: CaProjectLock[], handle: string, project = '', projectKey = ''): CaProjectLock | null {
  const aliases = new Set(caProjectAliases(project, handle, projectKey))
  const normalized = handle.trim().replace(/^@/, '').toLowerCase()
  for (const lock of locks) {
    if (lock.aliases.some((alias) => aliases.has(alias))) return lock
    if (normalized && lock.handle.replace(/^@/, '').toLowerCase() === normalized) return lock
  }
  return null
}

export function sharesLock(locks: CaProjectLock[], left: CaFind, right: CaFind): boolean {
  const lock = lockForFind(locks, left)
  return Boolean(lock && lockForFind(locks, right)?.id === lock.id)
}

export function sameProject(a: CaFind, b: CaFind): boolean {
  const left = new Set(caProjectAliases(a.project, a.handle, a.projectKey))
  return caProjectAliases(b.project, b.handle, b.projectKey).some((alias) => left.has(alias))
}

export function detectedMs(find: CaFind): number {
  const time = Date.parse(find.detected_at)
  return Number.isNaN(time) ? 0 : time
}

/** Checksum-only changes share an id. Empty input stays empty. */
export function caAddressId(address: string): string {
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
    caAddressId(find.address),
    find.source.trim().toLowerCase(),
    find.detected_at.trim(),
    find.evidence_url.trim(),
    find.caStatus,
    find.alertOk ? 'alert' : '',
    find.activity ? 'activity' : '',
    find.archived ? 'archived' : '',
  ].join('\n')
}

function asCount(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return 0
}

function asBoolOrNull(value: unknown): boolean | null {
  if (value === true || value === false) return value
  return null
}

function normalizeStatus(value: string): CaStatus {
  const key = value.trim().toLowerCase()
  return STATUSES.has(key) ? (key as CaStatus) : ''
}

function normalizeProvenance(value: unknown): CaProvenance {
  if (value == null) return ''
  const key = asString(value).toLowerCase()
  return PROVENANCES.has(key) ? (key as CaProvenance) : ''
}

function normalizeRole(value: unknown): CaRole {
  if (value == null) return ''
  const key = asString(value).toLowerCase()
  return ROLES.has(key) ? (key as CaRole) : ''
}

function isActivityRow(row: Record<string, unknown>, kind: string, status: string): boolean {
  if (row.activity === true || row.is_activity === true || row.wallet_activity === true) return true
  const key = kind.trim().toLowerCase()
  if (key === 'activity' || key === 'wallet_activity' || key === 'watched_activity') return true
  if (status === 'activity' || status === 'wallet_activity') return true
  const label = asString(row.label_zh || row.label)
  return label === '钱包动态' || label === '监控钱包动态'
}

interface ReadRowOptions {
  archived?: boolean
  activity?: boolean
  defaultStatus?: CaStatus
  inheritLock?: boolean
  inheritLockUrl?: string
}

function readCaRow(raw: unknown, options: ReadRowOptions = {}): CaFind | null {
  if (!raw || typeof raw !== 'object') return null
  const row = raw as Record<string, unknown>
  const address = asString(row.address)
  if (!address) return null
  const kind = asString(row.kind || row.addr_kind)
  const status = normalizeStatus(asString(row.ca_status || row.caStatus)) || options.defaultStatus || ''
  const activity = options.activity === true || isActivityRow(row, kind, status)
  const provenance = normalizeProvenance(row.provenance)
  const provenanceZh = asString(row.provenance_zh || row.provenanceZh) || (provenance ? PROVENANCE_ZH[provenance] : '')
  const statusZh =
    asString(row.ca_status_zh || row.caStatusZh) ||
    (activity && !status ? '钱包动态' : status ? STATUS_ZH[status] : '')
  const locked = row.ca_locked === true || options.inheritLock === true
  const lockUrl =
    asString(row.locked_by_official_x_url || row.lockedByOfficialXUrl) ||
    (locked ? options.inheritLockUrl || '' : '')
  return {
    project: asString(row.project),
    handle: asString(row.handle).replace(/^@/, ''),
    chain: asString(row.chain),
    address,
    source: normalizeCaSource(asString(row.source)),
    evidence_url: asString(row.evidence_url),
    detected_at: asString(row.detected_at),
    confidence: normalizeCaConfidence(asString(row.confidence)),
    note: asString(row.note),
    labelZh: asString(row.label_zh || row.label),
    caStatus: activity && status === 'confirmed' ? '' : status,
    caStatusZh: activity && status === 'confirmed' ? '钱包动态' : statusZh,
    provenance,
    provenanceZh,
    officialXConfirmed: row.official_x_confirmed === true || row.officialXConfirmed === true,
    walletFactoryConfirmed: row.wallet_factory_confirmed === true || row.walletFactoryConfirmed === true,
    officialXUrl: asString(row.official_x_url || row.officialXUrl),
    caRole: normalizeRole(row.ca_role || row.caRole),
    alertOk:
      !activity &&
      !options.archived &&
      (status === 'confirmed' || status === 'candidate') &&
      (row.alert_ok === true || row.alertOk === true),
    supersededBy: asString(row.superseded_by || row.supersededBy),
    pairedWith: asString(row.paired_with || row.pairedWith),
    confirmBasisZh: asString(row.confirm_basis_zh || row.confirmBasisZh),
    creator: asString(row.creator),
    creatorWatched: asBoolOrNull(row.creator_watched ?? row.creatorWatched),
    tx: asString(row.tx),
    cpu: asString(row.cpu),
    mintPriceBnb: asString(row.mint_price_bnb || row.mintPriceBnb),
    supplyCap: asString(row.supply_cap || row.supplyCap),
    processor: asString(row.processor),
    transistors: asString(row.transistors),
    caLocked: locked,
    lockUrl,
    projectKey: asString(row.project_key || row.projectKey).toLowerCase(),
    lockAt: asString(row.ca_locked_at || row.caLockedAt),
    activity,
    archived: options.archived === true,
  }
}

function pushUnique(bucket: CaFind[], seen: Set<string>, find: CaFind | null) {
  if (!find) return
  const key = caFindKey(find)
  if (seen.has(key)) return
  seen.add(key)
  bucket.push(find)
}

function readRows(value: unknown, options: ReadRowOptions, bucket: CaFind[], seen: Set<string>) {
  if (!Array.isArray(value)) return
  for (const item of value) pushUnique(bucket, seen, readCaRow(item, options))
}

function readStatusCounts(value: unknown): CaStatusCounts {
  if (!value || typeof value !== 'object') return { ...EMPTY_STATUS_COUNTS }
  const row = value as Record<string, unknown>
  return {
    confirmed: asCount(row.confirmed),
    candidate: asCount(row.candidate),
    superseded: asCount(row.superseded),
    not_ca: asCount(row.not_ca),
  }
}

const ACTIVITY_KEYS = ['wallet_activity', 'watched_wallet_activity', 'activity', 'activities'] as const
const LOCK_LIST_KEYS = ['ca_locked_projects', 'locked_projects', 'project_locks', 'locks', 'projects'] as const

function absorbProjectRecords(value: unknown, activity: CaFind[], activitySeen: Set<string>, locks: CaProjectLock[]) {
  if (!Array.isArray(value)) return
  for (const item of value) {
    if (typeof item === 'string' && item.trim()) {
      const key = item.trim().toLowerCase()
      locks.push({
        id: `k:${key}`,
        project: '',
        handle: key,
        url: '',
        aliases: [`k:${key}`, `h:${key}`],
      })
      continue
    }
    if (!item || typeof item !== 'object') continue
    const row = item as Record<string, unknown>
    const projectKey = asString(row.project_key || row.projectKey).toLowerCase()
    const url = asString(row.locked_by_official_x_url || row.lockedByOfficialXUrl)
    const locked = row.ca_locked === true || Boolean(url)
    const project = asString(row.project || row.name)
    const handle = asString(row.handle).replace(/^@/, '')
    if (locked && (project || handle || url)) {
      const aliases = caProjectAliases(project, handle, projectKey)
      if (aliases.length > 0) {
        locks.push({
          id: aliases[0],
          project,
          handle,
          url,
          aliases,
        })
      }
    }
    for (const key of ACTIVITY_KEYS) {
      readRows(row[key], { activity: true, inheritLock: locked, inheritLockUrl: url }, activity, activitySeen)
    }
  }
}

function locksFromRows(rows: CaFind[]): CaProjectLock[] {
  const byId = new Map<string, CaProjectLock>()
  for (const row of rows) {
    if (!row.caLocked && !row.lockUrl) continue
    const aliases = caProjectAliases(row.project, row.handle, row.projectKey)
    if (aliases.length === 0) continue
    const id = aliases[0]
    const prev = byId.get(id)
    if (!prev) {
      byId.set(id, { id, project: row.project, handle: row.handle, url: row.lockUrl, aliases })
      continue
    }
    if (!prev.url && row.lockUrl) prev.url = row.lockUrl
    if (!prev.project && row.project) prev.project = row.project
    for (const alias of aliases) {
      if (!prev.aliases.includes(alias)) prev.aliases.push(alias)
    }
  }
  return [...byId.values()]
}

function mergeLocks(lists: CaProjectLock[][]): CaProjectLock[] {
  const merged: CaProjectLock[] = []
  for (const lock of lists.flat()) {
    const hit = merged.find((item) => item.aliases.some((alias) => lock.aliases.includes(alias)))
    if (!hit) {
      merged.push({ ...lock, aliases: [...lock.aliases] })
      continue
    }
    if (!hit.url && lock.url) hit.url = lock.url
    if (!hit.project && lock.project) hit.project = lock.project
    if (!hit.handle && lock.handle) hit.handle = lock.handle
    for (const alias of lock.aliases) {
      if (!hit.aliases.includes(alias)) hit.aliases.push(alias)
    }
  }
  return merged
}

function applyLocks(rows: CaFind[], locks: CaProjectLock[]) {
  for (const row of rows) {
    const lock = lockForFind(locks, row)
    if (!lock) continue
    row.caLocked = true
    if (!row.lockUrl && lock.url) row.lockUrl = lock.url
  }
}

function sortFinds(rows: CaFind[]) {
  rows.sort((a, b) => detectedMs(b) - detectedMs(a) || a.address.localeCompare(b.address))
}

/** CA sound and the orange「新」highlight. Wallet activity, archived rows, and 已开盘 projects never qualify. */
export function alertableFinds(finds: CaFind[], launched: LaunchedItem[] = []): CaFind[] {
  return finds.filter(
    (find) => find.alertOk && !find.activity && !find.archived && matchLaunched(launched, find) == null,
  )
}

export function projectGroupKey(find: CaFind): string {
  const handle = find.handle.replace(/^@/, '').trim().toLowerCase()
  if (handle) return `h:${handle}`
  const project = find.project.trim().toLowerCase()
  if (project) return `p:${project}`
  return `a:${caAddressId(find.address)}`
}

export function parseCaFinds(data: unknown): CaFindsPayload {
  if (!data || typeof data !== 'object') throw new Error('无效的 JSON')
  const obj = data as Record<string, unknown>
  if (!Array.isArray(obj.finds)) throw new Error('JSON 需包含 finds 数组')

  const activeSeen = new Set<string>()
  const active: CaFind[] = []
  readRows(obj.finds, {}, active, activeSeen)

  const suspectedSeen = new Set<string>()
  const suspected: CaFind[] = []
  readRows(obj.suspected_copycats, { defaultStatus: 'suspected_copycat' }, suspected, suspectedSeen)

  const archiveSeen = new Set<string>()
  const archive: CaFind[] = []
  const activitySeen = new Set<string>()
  const activity: CaFind[] = []

  const finds: CaFind[] = []
  for (const find of active) {
    if (find.activity) {
      pushUnique(activity, activitySeen, find)
      continue
    }
    if (find.caStatus === 'suspected_copycat') {
      pushUnique(suspected, suspectedSeen, find)
      continue
    }
    if (find.caStatus === 'superseded') {
      pushUnique(archive, archiveSeen, find)
      continue
    }
    finds.push(find)
  }

  const launchedSeen = new Set<string>()
  const launchedArchive: CaFind[] = []
  if (Array.isArray(obj.launched_history)) {
    for (const item of obj.launched_history) {
      const row = readCaRow(item, { archived: true })
      if (!row) continue
      const sameAddress = (prev: CaFind) =>
        caAddressId(prev.address) === caAddressId(row.address) && prev.chain.toLowerCase() === row.chain.toLowerCase()
      if (row.caStatus === 'superseded') {
        if (archive.some(sameAddress)) continue
        pushUnique(archive, archiveSeen, row)
        continue
      }
      if (row.caStatus !== 'confirmed') continue
      if (finds.some(sameAddress) || launchedArchive.some(sameAddress)) continue
      pushUnique(launchedArchive, launchedSeen, row)
    }
  }

  const declaredLocks: CaProjectLock[] = []
  for (const key of LOCK_LIST_KEYS) absorbProjectRecords(obj[key], activity, activitySeen, declaredLocks)
  for (const key of ACTIVITY_KEYS) readRows(obj[key], { activity: true }, activity, activitySeen)

  const known = new Set([...finds, ...suspected, ...archive, ...launchedArchive].map((find) => caAddressId(find.address)))
  const walletActivity = activity.filter((find) => !known.has(caAddressId(find.address)))

  const locks = mergeLocks([
    declaredLocks,
    locksFromRows([...finds, ...suspected, ...archive, ...launchedArchive, ...walletActivity]),
  ])
  applyLocks([...finds, ...suspected, ...archive, ...launchedArchive, ...walletActivity], locks)

  sortFinds(finds)
  sortFinds(suspected)
  sortFinds(archive)
  sortFinds(launchedArchive)
  sortFinds(walletActivity)

  const statusCounts = readStatusCounts(obj.status_counts)
  const suspectedCopycatCount = asCount(obj.suspected_copycat_count) || suspected.length
  return {
    generated_at: typeof obj.generated_at === 'string' ? obj.generated_at : undefined,
    schemaVersion: typeof obj.schema_version === 'number' ? obj.schema_version : undefined,
    confidenceModel: typeof obj.confidence_model === 'string' ? obj.confidence_model : undefined,
    statusCounts,
    confirmedCount: asCount(obj.confirmed_count) || statusCounts.confirmed,
    candidateCount: asCount(obj.candidate_count) || statusCounts.candidate,
    suspectedCopycatCount,
    finds,
    suspectedCopycats: suspected,
    supersededArchive: archive,
    launchedArchive,
    walletActivity,
    locks,
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
    const hay = `${find.project} ${find.handle} ${find.address} ${find.labelZh} ${find.creator} ${find.confirmBasisZh}`.toLowerCase()
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
