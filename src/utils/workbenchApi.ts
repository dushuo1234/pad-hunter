import type { Candidate } from '../types'
import { findByHandle } from './candidates'
import { xProfileUrl } from './format'
import { launchedMarkBody, siteClientIdFrom } from './launchedMark'
import { parsePinResponse, parseReviewResponse, type PinMergeState, type ReviewWire } from './syncMerge'
import { handleKey, safeHttpUrl, type WorkbenchItem } from './workbench'
import { parseWorkbenchAlertsPayload, WORKBENCH_ALERTS_PATH, type WorkbenchAlert } from './workbenchAlerts'
import { FALLBACK_WORKBENCH_API_BASE, migratedWorkbenchApiBase } from './apiBase'

/** Used when `VITE_WORKBENCH_API_BASE` is unset. The token is never stored here. */
export { FALLBACK_WORKBENCH_API_BASE }

export const API_SETTINGS_KEY = 'pad-hunter.workbench.api'
export const CLIENT_ID_KEY = 'pad-hunter.workbench.client'

function launchedUrl(): string {
  const base = import.meta.env?.BASE_URL || '/'
  return `${base}data/launched.json`
}

export interface ApiSettings {
  token: string
  /** Empty means the env override or the fallback host. */
  baseUrl: string
}

export interface HealthInfo {
  ok: boolean
  version: string
  workbenchCount: number | null
  pollerAlive: boolean | null
  pollerTargetMode: string
}

export type SiteStatus = 'up' | 'down' | 'unknown'

export interface WorkbenchStatusItem {
  handle: string
  name: string
  url: string
  polled: boolean
  siteStatus: SiteStatus
  httpCode: string
  lastError: string
  lastCheckAt: string
  lastLatencyMs: number | null
  intervalS: number | null
  changeCount: number
  lastChangeAt: string
  addressCount: number
  lastAddresses: string[]
  push: boolean | null
  listingAt: string
  listingSource: string
  listingEvidenceUrl: string
  alreadyListed: boolean
  checking: boolean
  lastManualResult: string
  crawlCount: number | null
}

export interface WorkbenchStatus {
  pollerAlive: boolean | null
  pollerTargetMode: string
  items: WorkbenchStatusItem[]
}

export interface WorkbenchChange {
  id: string
  text: string
  at: string
  tone: 'danger' | 'warn' | 'info'
}

export interface CrawlRecord {
  id: string
  at: string
  httpCode: string
  bytes: number | null
  latencyMs: number | null
  error: string
}

export interface FoundAddress {
  address: string
  chain: string
  label: string
}

export interface WorkbenchDetail {
  recentChanges: WorkbenchChange[]
  crawlHistory: CrawlRecord[]
  addresses: FoundAddress[]
  crawlCount: number | null
}

export interface SyncItem {
  handle: string
  name: string
  sites: string[]
  x_url: string
  chain: string
  notes: string
  push: boolean
}

export interface LaunchedIndex {
  handles: Set<string>
  names: Set<string>
}

export interface ApiError {
  status: number
  message: string
  body?: unknown
}

export interface WorkbenchSyncResult {
  count: number
  droppedLaunched: string[]
}

const EMPTY_SETTINGS: ApiSettings = { token: '', baseUrl: '' }
const EMPTY_LAUNCHED: LaunchedIndex = { handles: new Set(), names: new Set() }

const COUNT_KEYS = ['crawl_count', 'poll_count', 'total_crawls', 'fetch_count', 'checks', 'crawl_total', 'polled_count', 'total']

let settings: ApiSettings = loadSettings()
const listeners = new Set<() => void>()

function envBase(): string {
  try {
    const value = import.meta.env.VITE_WORKBENCH_API_BASE
    if (typeof value === 'string' && value.trim()) return stripSlash(value.trim())
  } catch {
    // import.meta.env is absent outside Vite.
  }
  return ''
}

export function defaultApiBase(): string {
  return envBase() || FALLBACK_WORKBENCH_API_BASE
}

export function resolveApiBase(override: string): string {
  const custom = override.trim()
  if (!custom) return defaultApiBase()
  return stripSlash(custom)
}

function stripSlash(value: string): string {
  return value.replace(/\/+$/, '')
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  return ''
}

function asNumber(value: unknown): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && Number.isFinite(Number(value))) return Number(value)
  return null
}

function asBool(value: unknown): boolean | null {
  if (typeof value === 'boolean') return value
  if (value === 1 || value === '1' || value === 'true') return true
  if (value === 0 || value === '0' || value === 'false') return false
  return null
}

function pickString(row: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const text = asString(row[key])
    if (text) return text
  }
  return ''
}

function pickNumber(row: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = asNumber(row[key])
    if (value != null) return value
  }
  return null
}

function asArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value
  const row = asRecord(value)
  if (!row) return []
  for (const key of ['items', 'list', 'rows', 'data', 'results', 'addresses']) {
    if (Array.isArray(row[key])) return row[key]
  }
  return []
}

function storageGet(key: string): string | null {
  if (typeof localStorage === 'undefined') return null
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function storageSet(key: string, value: string): void {
  if (typeof localStorage === 'undefined') return
  try {
    localStorage.setItem(key, value)
  } catch {
    // Keep the in-memory copy if the browser refuses the write.
  }
}

function loadSettings(): ApiSettings {
  const raw = storageGet(API_SETTINGS_KEY)
  if (!raw) return EMPTY_SETTINGS
  try {
    const row = asRecord(JSON.parse(raw))
    if (!row) return EMPTY_SETTINGS
    const token = asString(row.token)
    const savedBase = asString(row.baseUrl || row.base_url)
    const baseUrl = migratedWorkbenchApiBase(savedBase)
    if (baseUrl !== savedBase) storageSet(API_SETTINGS_KEY, JSON.stringify({ token, baseUrl }))
    return { token, baseUrl }
  } catch {
    return EMPTY_SETTINGS
  }
}

export function getApiSettings(): ApiSettings {
  return settings
}

export function subscribeApiSettings(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange)
  const onStorage = (event: StorageEvent) => {
    if (event.key != null && event.key !== API_SETTINGS_KEY) return
    settings = loadSettings()
    onStoreChange()
  }
  window.addEventListener('storage', onStorage)
  return () => {
    listeners.delete(onStoreChange)
    window.removeEventListener('storage', onStorage)
  }
}

function commitSettings(next: ApiSettings) {
  settings = next
  storageSet(API_SETTINGS_KEY, JSON.stringify(next))
  for (const listener of listeners) listener()
}

export function validateApiBase(value: string): string {
  const trimmed = value.trim()
  if (!trimmed) return ''
  let url: URL
  try {
    url = new URL(trimmed)
  } catch {
    throw new Error('接口地址需要是 http(s) URL')
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') throw new Error('接口地址需要是 http(s) URL')
  return stripSlash(url.toString())
}

export function saveApiSettings(input: { token: string; baseUrl: string }): void {
  commitSettings({
    token: input.token.trim(),
    baseUrl: validateApiBase(input.baseUrl),
  })
}

export function clearApiToken(): void {
  commitSettings({ ...settings, token: '' })
}

export function getClientId(): string {
  const existing = storageGet(CLIENT_ID_KEY)?.trim() ?? ''
  if (existing) return existing
  const created = crypto.randomUUID()
  storageSet(CLIENT_ID_KEY, created)
  return created
}

/** `site-<deviceId>` sent on `POST /v1/launched/mark`. Pin sync keeps the raw device id. */
export function siteClientId(): string {
  return siteClientIdFrom(getClientId())
}

function candidateRecord(candidate: Candidate | undefined): Record<string, unknown> | null {
  if (!candidate) return null
  return candidate as unknown as Record<string, unknown>
}

export function sitesForPin(item: WorkbenchItem, candidate: Candidate | undefined): string[] {
  const row = candidateRecord(candidate)
  const raw: unknown[] = []
  if (row) {
    if (Array.isArray(row.sites)) raw.push(...row.sites)
    else if (typeof row.sites === 'string') raw.push(row.sites)
    if (typeof row.site === 'string') raw.push(row.site)
  }
  if (item.siteUrl) raw.push(item.siteUrl)
  const sites: string[] = []
  const seen = new Set<string>()
  for (const value of raw) {
    const url = safeHttpUrl(asString(value))
    if (!url || seen.has(url)) continue
    seen.add(url)
    sites.push(url)
  }
  return sites
}

export function chainForPin(item: WorkbenchItem, candidate: Candidate | undefined): string {
  const chain = candidate?.chain?.trim() || item.caChain.trim()
  return chain
}

export function xUrlForPin(item: WorkbenchItem, candidate: Candidate | undefined): string {
  const row = candidateRecord(candidate)
  const explicit = safeHttpUrl(asString(row?.x_url))
  if (explicit) return explicit
  const tweet = safeHttpUrl(candidate?.tweet_url || '')
  if (tweet) return tweet
  const handle = item.handle.trim()
  return handle ? xProfileUrl(handle) : ''
}

export function syncItemsFromPins(items: WorkbenchItem[], candidates: Candidate[]): SyncItem[] {
  const synced: SyncItem[] = []
  for (const item of items) {
    const handle = item.handle.trim()
    if (!handle) continue
    const candidate = findByHandle(candidates, handle)
    synced.push({
      handle,
      name: item.name.trim() || handle,
      sites: sitesForPin(item, candidate),
      x_url: xUrlForPin(item, candidate),
      chain: chainForPin(item, candidate),
      notes: item.notes,
      push: item.push,
    })
  }
  return synced
}

function errorMessage(status: number, body: unknown): string {
  const detail = asString(asRecord(body)?.detail)
  if (status === 401) return '令牌无效或缺失'
  if (detail && !detail.startsWith('<')) return detail.slice(0, 180)
  if (status === 0) return '无法连接监控接口'
  return `监控接口错误 (${status})`
}

export function isAuthError(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && (error as ApiError).status === 401)
}

export function isNotFound(error: unknown): boolean {
  return Boolean(error && typeof error === 'object' && (error as ApiError).status === 404)
}

/** Status, detail, and check are absent on the sync worker. 401/404/network stay off the sync hint. */
export function isUnavailable(error: unknown): boolean {
  if (!error || typeof error !== 'object') return false
  const status = (error as ApiError).status
  return status === 0 || status === 401 || status === 404
}

const unsupportedRoutes = new Set<string>()

function unsupportedRouteKey(base: string, token: string, path: string): string {
  return `${stripSlash(base)}\n${token}\n${path.split('?')[0]}`
}

function unsupportedRoute(base: string, token: string, path: string): ApiError | null {
  if (!unsupportedRoutes.has(unsupportedRouteKey(base, token, path))) return null
  return { status: 404, message: '监控接口错误 (404)' }
}

function rememberUnsupported(base: string, token: string, path: string, error: unknown): void {
  if (!isUnavailable(error) || !error || typeof error !== 'object') return
  const status = (error as ApiError).status
  if (status === 401 || status === 404) unsupportedRoutes.add(unsupportedRouteKey(base, token, path))
}

export function errorText(error: unknown): string {
  if (error && typeof error === 'object' && 'message' in error && typeof error.message === 'string' && error.message) {
    return error.message
  }
  if (error instanceof Error && error.message) return error.message
  return '无法连接监控接口'
}

function allowsNgrokBypass(base: string): boolean {
  try {
    return new URL(base).hostname.toLowerCase().includes('ngrok')
  } catch {
    return base.toLowerCase().includes('ngrok')
  }
}

/** `Retry-After` as a delay. A bare `1` is one second. Missing or unreadable values wait 1s. */
export function retryAfterMs(header: string | null, now = Date.now()): number {
  const text = header?.trim() ?? ''
  if (!text) return 1000
  const seconds = Number(text)
  if (Number.isFinite(seconds) && seconds >= 0) return Math.min(30_000, Math.round(seconds * 1000))
  const at = Date.parse(text)
  if (Number.isFinite(at)) return Math.min(30_000, Math.max(0, at - now))
  return 1000
}

async function apiFetch(base: string, path: string, token: string, init?: RequestInit, timeoutMs = 10000, retried = false): Promise<unknown> {
  const headers = new Headers(init?.headers)
  if (allowsNgrokBypass(base)) headers.set('ngrok-skip-browser-warning', '1')
  if (token) headers.set('X-Pad-Hunter-Token', token)
  if (init?.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  let response: Response
  try {
    response = await fetch(`${stripSlash(base)}${path}`, {
      ...init,
      headers,
      cache: 'no-store',
      signal: AbortSignal.timeout(timeoutMs),
    })
  } catch (error) {
    const name = error instanceof Error ? error.name : ''
    const failure: ApiError = {
      status: 0,
      message: name === 'TimeoutError' || name === 'AbortError' ? '监控接口超时' : '无法连接监控接口',
    }
    throw failure
  }
  const text = await response.text()
  let body: unknown = null
  if (text) {
    try {
      body = JSON.parse(text)
    } catch {
      body = null
    }
  }
  if (!response.ok) {
    if (response.status === 503 && !retried) {
      await new Promise((resolve) => setTimeout(resolve, retryAfterMs(response.headers.get('Retry-After'))))
      return apiFetch(base, path, token, init, timeoutMs, true)
    }
    const failure: ApiError = { status: response.status, message: errorMessage(response.status, body), body }
    throw failure
  }
  if (text && body == null) {
    const failure: ApiError = { status: response.status, message: '接口返回的不是 JSON' }
    throw failure
  }
  return body
}

export async function fetchHealth(base: string, token = ''): Promise<HealthInfo> {
  const body = await apiFetch(base, '/health', token, undefined, 8000)
  const row = asRecord(body) ?? {}
  return {
    ok: row.ok !== false,
    version: asString(row.version),
    workbenchCount: asNumber(row.workbench_count),
    pollerAlive: asBool(row.poller_alive),
    pollerTargetMode: asString(row.poller_target_mode),
  }
}

export function droppedLaunchedHandles(body: unknown): string[] {
  const row = asRecord(body)
  if (!row) return []
  const raw = row.dropped_launched ?? row.droppedLaunched
  if (raw == null || typeof raw === 'number' || typeof raw === 'boolean') return []
  const entries = Array.isArray(raw) ? raw : [raw]
  const found: string[] = []
  const seen = new Set<string>()
  for (const entry of entries) {
    let handle = ''
    if (typeof entry === 'string' || typeof entry === 'number') handle = asString(entry)
    else {
      const record = asRecord(entry)
      if (record) handle = asString(record.handle ?? record.x ?? record.twitter)
    }
    const key = handleKey(handle)
    if (!key || seen.has(key)) continue
    seen.add(key)
    found.push(key)
  }
  return found
}

export async function syncWorkbench(base: string, token: string, items: SyncItem[]): Promise<WorkbenchSyncResult> {
  const body = await apiFetch(
    base,
    '/v1/workbench/sync',
    token,
    {
      method: 'POST',
      body: JSON.stringify({ items, client_id: getClientId() }),
    },
    15000,
  )
  if (typeof body === 'number' && Number.isFinite(body)) return { count: body, droppedLaunched: [] }
  const row = asRecord(body)
  const count = row ? pickNumber(row, ['count', 'workbench_count', 'synced']) : null
  return {
    count: count ?? items.length,
    droppedLaunched: droppedLaunchedHandles(body),
  }
}

export async function fetchPins(base: string, token: string): Promise<{ syncedAt: string; state: PinMergeState }> {
  const body = await apiFetch(base, '/v1/workbench/pins', token)
  const parsed = parsePinResponse(body)
  if (!parsed) {
    const failure: ApiError = { status: 200, message: '接口返回的不是钉选列表' }
    throw failure
  }
  return { syncedAt: parsed.syncedAt, state: parsed.state }
}

export async function pushMergedPins(
  base: string,
  token: string,
  state: PinMergeState,
): Promise<{ state: PinMergeState | null; droppedLaunched: string[] }> {
  const body = await apiFetch(
    base,
    '/v1/workbench/sync',
    token,
    {
      method: 'POST',
      body: JSON.stringify({
        client_id: getClientId(),
        items: state.items,
        removed: state.removed,
      }),
    },
    15000,
  )
  return {
    state: parsePinResponse(body)?.state ?? null,
    droppedLaunched: droppedLaunchedHandles(body),
  }
}

export async function fetchReviewed(base: string, token: string): Promise<{ syncedAt: string; marks: Record<string, ReviewWire> }> {
  const body = await apiFetch(base, '/v1/workbench/reviewed', token)
  const parsed = parseReviewResponse(body)
  if (!parsed) {
    const failure: ApiError = { status: 200, message: '接口返回的不是已看记录' }
    throw failure
  }
  return parsed
}

export async function pushMergedReviewed(
  base: string,
  token: string,
  marks: Record<string, ReviewWire>,
): Promise<Record<string, ReviewWire> | null> {
  const body = await apiFetch(
    base,
    '/v1/workbench/reviewed/sync',
    token,
    {
      method: 'POST',
      body: JSON.stringify({ client_id: getClientId(), marks }),
    },
    15000,
  )
  return parseReviewResponse(body)?.marks ?? null
}

export async function checkWorkbench(base: string, token: string, handle: string): Promise<boolean> {
  const path = '/v1/workbench/check'
  const skipped = unsupportedRoute(base, token, path)
  if (skipped) throw skipped
  let body: unknown
  try {
    body = await apiFetch(
      base,
      path,
      token,
      {
        method: 'POST',
        body: JSON.stringify({ handle }),
      },
      15000,
    )
  } catch (error) {
    rememberUnsupported(base, token, path, error)
    throw error
  }
  const queued = asRecord(body)?.queued
  if (queued === false || queued === 'false' || queued === 0) return false
  return true
}

function parseSiteStatus(value: unknown): SiteStatus {
  const text = asString(value).toLowerCase()
  if (text === 'up' || text === 'ok' || text === 'online' || text === '已上线') return 'up'
  if (text === 'down' || text === 'offline' || text === 'error' || text === '未上线' || text === 'fail' || text === 'failed') {
    return 'down'
  }
  return 'unknown'
}

function parseListingAt(value: unknown): string {
  const text = asString(value)
  if (!text || text === '未知' || text.toLowerCase() === 'unknown' || text === 'null') return '未知'
  return text
}

function parseAddresses(value: unknown): string[] {
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  const found: string[] = []
  const seen = new Set<string>()
  for (const entry of asArray(value)) {
    const address = typeof entry === 'string' ? entry.trim() : pickString(asRecord(entry) ?? {}, ['address', 'ca', 'contract', 'addr', 'token'])
    if (!address) continue
    const key = address.toLowerCase()
    if (seen.has(key)) continue
    seen.add(key)
    found.push(address)
  }
  return found
}

function parseStatusItem(raw: unknown): WorkbenchStatusItem | null {
  const row = asRecord(raw)
  if (!row) return null
  const handle = asString(row.handle).replace(/^@/, '')
  if (!handle) return null
  const addresses = parseAddresses(row.last_addresses ?? row.addresses ?? row.address_list)
  const addressCount = pickNumber(row, ['address_count', 'addresses_count', 'addr_count']) ?? addresses.length
  const latency = pickNumber(row, ['last_latency_ms', 'latency_ms', 'time_ms'])
  const latencyS = pickNumber(row, ['time_s', 'last_time_s'])
  return {
    handle,
    name: asString(row.name),
    url: safeHttpUrl(pickString(row, ['url', 'site', 'site_url', 'final_url'])),
    polled: asBool(row.polled) ?? false,
    siteStatus: parseSiteStatus(row.site_status ?? row.status),
    httpCode: asString(row.http_code ?? row.status_code).replace(/\.0$/, ''),
    lastError: asString(row.last_error ?? row.error),
    lastCheckAt: pickString(row, ['last_check_at', 'checked_at', 'last_polled_at']),
    lastLatencyMs: latency ?? (latencyS != null ? Math.round(latencyS * 1000) : null),
    intervalS: pickNumber(row, ['interval_s', 'interval', 'poll_interval_s']),
    changeCount: pickNumber(row, ['change_count', 'changes']) ?? 0,
    lastChangeAt: pickString(row, ['last_change_at', 'changed_at']),
    addressCount,
    lastAddresses: addresses,
    push: asBool(row.push),
    listingAt: parseListingAt(row.listing_at),
    listingSource: asString(row.listing_source),
    listingEvidenceUrl: safeHttpUrl(asString(row.listing_evidence_url)),
    alreadyListed: asBool(row.already_listed) ?? false,
    checking: asBool(row.checking) ?? false,
    lastManualResult: asString(row.last_manual_result),
    crawlCount: pickNumber(row, COUNT_KEYS),
  }
}

export function parseStatusPayload(data: unknown): WorkbenchStatus {
  const row = asRecord(data)
  const list = asArray(row?.items ?? row?.targets ?? data)
  const items: WorkbenchStatusItem[] = []
  const seen = new Set<string>()
  for (const entry of list) {
    const item = parseStatusItem(entry)
    if (!item) continue
    const key = handleKey(item.handle)
    if (!key || seen.has(key)) continue
    seen.add(key)
    items.push(item)
  }
  return {
    pollerAlive: row ? asBool(row.poller_alive) : null,
    pollerTargetMode: row ? asString(row.poller_target_mode) : '',
    items,
  }
}

export async function fetchWorkbenchAlerts(base: string, token: string): Promise<WorkbenchAlert[]> {
  const path = WORKBENCH_ALERTS_PATH
  const skipped = unsupportedRoute(base, token, path)
  if (skipped) throw skipped
  try {
    const body = await apiFetch(base, path, token)
    return parseWorkbenchAlertsPayload(body)
  } catch (error) {
    rememberUnsupported(base, token, path, error)
    throw error
  }
}

export async function fetchStatus(base: string, token: string): Promise<WorkbenchStatus> {
  const path = '/v1/workbench/status'
  const skipped = unsupportedRoute(base, token, path)
  if (skipped) throw skipped
  try {
    const body = await apiFetch(base, path, token)
    return parseStatusPayload(body)
  } catch (error) {
    rememberUnsupported(base, token, path, error)
    throw error
  }
}

function changeTone(text: string, kind: string): WorkbenchChange['tone'] {
  const hay = `${kind} ${text}`.toLowerCase()
  if (/版本|frontend|hash|error|fail|down|危险|异常/.test(hay)) return 'danger'
  if (/内容|新增|移除|content/.test(hay)) return 'warn'
  return 'info'
}

function parseChange(raw: unknown, index: number): WorkbenchChange | null {
  if (typeof raw === 'string' && raw.trim()) {
    const text = raw.trim().slice(0, 500)
    return { id: `c${index}`, text, at: '', tone: changeTone(text, '') }
  }
  const row = asRecord(raw)
  if (!row) return null
  const kind = pickString(row, ['kind', 'type', 'category', 'level'])
  let text = pickString(row, ['summary', 'message', 'text', 'title', 'description', 'change', 'detail'])
  const added = pickNumber(row, ['added', 'added_lines', 'lines_added'])
  const removed = pickNumber(row, ['removed', 'removed_lines', 'lines_removed'])
  if (!text && (added != null || removed != null)) {
    text = `${kind || '页面内容变更'}：新增 ${added ?? 0} 行，移除 ${removed ?? 0} 行`
  }
  const hashes = asArray(row.hashes ?? row.versions)
    .map((entry) => asString(entry))
    .filter(Boolean)
  const hash = pickString(row, ['hash', 'version', 'frontend_version', 'build']) || hashes.join(', ')
  if (!text && hash) text = `${kind || '前端版本更新'}：${hash}`
  if (!text && kind) text = kind
  if (!text) return null
  const at = pickString(row, ['at', 'time', 'ts', 'created_at', 'detected_at', 'changed_at'])
  return {
    id: pickString(row, ['id']) || `c${index}`,
    text: text.slice(0, 500),
    at,
    tone: changeTone(text, kind),
  }
}

function parseCrawl(raw: unknown, index: number): CrawlRecord | null {
  const row = typeof raw === 'string' ? { text: raw } : asRecord(raw)
  if (!row) return null
  const at = pickString(row, ['at', 'time', 'ts', 'checked_at', 'crawled_at', 'created_at', 'timestamp'])
  const httpCode = asString(row.http_code ?? row.status_code ?? row.code).replace(/\.0$/, '')
  const bytes = pickNumber(row, ['bytes', 'size', 'body_bytes', 'content_length', 'length'])
  const latencyMs = pickNumber(row, ['latency_ms', 'time_ms', 'elapsed_ms', 'duration_ms', 'last_latency_ms'])
  const latencyS = pickNumber(row, ['time_s', 'elapsed_s', 'duration_s'])
  const error = pickString(row, ['error', 'last_error'])
  const text = pickString(row, ['text', 'line', 'summary'])
  if (!at && !httpCode && bytes == null && latencyMs == null && !error && !text) return null
  return {
    id: pickString(row, ['id']) || `h${index}`,
    at: at || text,
    httpCode,
    bytes,
    latencyMs: latencyMs ?? (latencyS != null ? Math.round(latencyS * 1000) : null),
    error,
  }
}

function addressKey(chain: string, address: string): string {
  const normalized = address.startsWith('0x') || address.startsWith('0X') ? address.toLowerCase() : address
  return `${chain.trim().toLowerCase()}\n${normalized}`
}

function parseFoundAddress(raw: unknown, fallbackChain: string): FoundAddress | null {
  if (typeof raw === 'string' && raw.trim()) return { address: raw.trim(), chain: fallbackChain, label: '' }
  const row = asRecord(raw)
  if (!row) return null
  const address = pickString(row, ['address', 'ca', 'contract', 'addr', 'token'])
  if (!address) return null
  return {
    address,
    chain: pickString(row, ['chain', 'ca_chain', 'network']) || fallbackChain,
    label: pickString(row, ['label', 'name', 'symbol', 'note']),
  }
}

export function parseDetailPayload(data: unknown, fallbackChain = ''): WorkbenchDetail {
  const row = asRecord(data) ?? {}
  const changes = asArray(row.recent_changes ?? row.changes)
    .map(parseChange)
    .filter((entry): entry is WorkbenchChange => Boolean(entry))
    .sort((a, b) => timeValue(b.at) - timeValue(a.at))
    .slice(0, 30)
  const history = asArray(row.crawl_history ?? row.history ?? row.crawls ?? row.polls)
    .map(parseCrawl)
    .filter((entry): entry is CrawlRecord => Boolean(entry))
    .sort((a, b) => timeValue(b.at) - timeValue(a.at))
    .slice(0, 100)
  const addresses: FoundAddress[] = []
  const seen = new Set<string>()
  for (const entry of [...asArray(row.addresses), ...asArray(row.ca_finds ?? row.cas)]) {
    const found = parseFoundAddress(entry, fallbackChain)
    if (!found) continue
    const key = addressKey(found.chain, found.address)
    if (seen.has(key)) continue
    seen.add(key)
    addresses.push(found)
  }
  return {
    recentChanges: changes,
    crawlHistory: history,
    addresses,
    crawlCount: pickNumber(row, COUNT_KEYS),
  }
}

function timeValue(iso: string): number {
  const value = Date.parse(iso)
  return Number.isNaN(value) ? 0 : value
}

export async function fetchDetail(base: string, token: string, handle: string, fallbackChain = ''): Promise<WorkbenchDetail> {
  const path = '/v1/workbench/detail'
  const skipped = unsupportedRoute(base, token, path)
  if (skipped) throw skipped
  try {
    const body = await apiFetch(base, `${path}?handle=${encodeURIComponent(handle)}`, token)
    return parseDetailPayload(body, fallbackChain)
  } catch (error) {
    rememberUnsupported(base, token, path, error)
    throw error
  }
}

export function parseLaunched(data: unknown): LaunchedIndex {
  const handles = new Set<string>()
  const names = new Set<string>()
  const visit = (value: unknown, depth: number, inList: boolean) => {
    if (!value || depth > 5) return
    if (typeof value === 'string') {
      if (!inList) return
      const text = value.trim()
      if (!text || text === '未知') return
      if (text.startsWith('@') || /^[A-Za-z0-9_]{2,32}$/.test(text)) handles.add(handleKey(text))
      else names.add(text.toLowerCase())
      return
    }
    if (Array.isArray(value)) {
      for (const entry of value) visit(entry, depth + 1, true)
      return
    }
    const row = asRecord(value)
    if (!row) return
    if (inList) {
      const handle = asString(row.handle || row.x || row.twitter).replace(/^@/, '')
      const name = asString(row.name || row.project)
      if (handle) handles.add(handleKey(handle))
      if (name) names.add(name.toLowerCase())
    }
    for (const key of ['handles', 'projects', 'items', 'launched', 'candidates', 'names', 'list']) {
      if (key in row) visit(row[key], depth + 1, false)
    }
  }
  visit(data, 0, false)
  handles.delete('')
  names.delete('')
  return { handles, names }
}

export function emptyLaunched(): LaunchedIndex {
  return EMPTY_LAUNCHED
}

export function isLaunched(index: LaunchedIndex, item: { handle: string; name: string }): boolean {
  const handle = handleKey(item.handle)
  if (handle && index.handles.has(handle)) return true
  const name = item.name.trim().toLowerCase()
  return Boolean(name && index.names.has(name))
}

export async function fetchLaunched(): Promise<LaunchedIndex> {
  try {
    const response = await fetch(launchedUrl(), { cache: 'no-cache' })
    if (!response.ok) return emptyLaunched()
    return parseLaunched(await response.json())
  } catch {
    return emptyLaunched()
  }
}

export async function postLaunchedMark(
  base: string,
  token: string,
  input: { handle: string; name?: string; at?: string },
): Promise<unknown> {
  return apiFetch(
    base,
    '/v1/launched/mark',
    token,
    {
      method: 'POST',
      body: JSON.stringify(launchedMarkBody({ ...input, clientId: siteClientId() })),
    },
    15000,
  )
}

export async function fetchLaunchedRecent(base: string, token: string): Promise<unknown | null> {
  try {
    return await apiFetch(base, '/v1/launched/recent', token, undefined, 8000)
  } catch (error) {
    if (isAuthError(error)) throw error
    return null
  }
}

export async function fetchBlocklist(base: string, token: string): Promise<unknown | null> {
  try {
    return await apiFetch(base, '/v1/workbench/blocklist', token, undefined, 8000)
  } catch (error) {
    if (isAuthError(error)) throw error
    return null
  }
}

/** Recent radar cards. Public for the github.io origin; a saved token is sent when present. */
export async function fetchRadarRecent(base: string, token: string): Promise<unknown | null> {
  try {
    return await apiFetch(base, '/v1/radar/recent', token, undefined, 8000)
  } catch {
    return null
  }
}

export function statusIndex(items: WorkbenchStatusItem[]): Map<string, WorkbenchStatusItem> {
  const map = new Map<string, WorkbenchStatusItem>()
  for (const item of items) {
    const key = handleKey(item.handle)
    if (key && !map.has(key)) map.set(key, item)
  }
  return map
}
