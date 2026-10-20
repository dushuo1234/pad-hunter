import type {
  Candidate,
  FactoryDeploy,
  ListingSignal,
  MonitorDocument,
  MonitorEvent,
  MonitorKind,
  SiteProbe,
} from '../types'

const KINDS = new Set<MonitorKind>(['site', 'listing_signal', 'ca', 'factory'])

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

function asNumber(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() && !Number.isNaN(Number(value))) return Number(value)
  return undefined
}

function handleOf(row: Record<string, unknown>): string {
  return asString(row.handle || row.twitter_handle).replace(/^@/, '')
}

function stamp(kind: string, handle: string, at: string, extra: string): string {
  return [kind, handle.toLowerCase(), at, extra].filter(Boolean).join('|')
}

function siteStatusValue(row: Record<string, unknown>): string {
  const status = asString(row.status)
  if (status) return status
  if (row.ok === true) return 'up'
  if (row.ok === false) return 'down'
  return ''
}

function siteFrom(row: Record<string, unknown>, handle: string, name: string): SiteProbe | null {
  const url = asString(row.url)
  if (!url) return null
  const error = asString(row.error)
  const finalUrl = asString(row.final_url)
  return {
    url,
    status: siteStatusValue(row) || undefined,
    ok: typeof row.ok === 'boolean' ? row.ok : undefined,
    http_code: asString(row.http_code) || undefined,
    time_s: asNumber(row.time_s),
    final_url: finalUrl || undefined,
    error: error || undefined,
    name: name || undefined,
    handle: handle || undefined,
  }
}

function push(out: MonitorEvent[], event: MonitorEvent | null) {
  if (event) out.push(event)
}

function normalizeCa(value: unknown): { ca: string; ca_chain: string; ca_source: string } | null {
  if (typeof value === 'string' && value.trim()) {
    return { ca: value.trim(), ca_chain: '', ca_source: '' }
  }
  const row = asRecord(value)
  if (!row) return null
  const ca = asString(row.ca || row.address || row.token)
  if (!ca) return null
  return {
    ca,
    ca_chain: asString(row.ca_chain || row.chain),
    ca_source: asString(row.ca_source || row.source),
  }
}

function eventFromNormalized(row: Record<string, unknown>, fallbackAt: string): MonitorEvent | null {
  const kind = asString(row.kind)
  if (!KINDS.has(kind as MonitorKind)) return null
  const handle = handleOf(row)
  if (!handle) return null
  const at = asString(row.at || row.checked_at) || fallbackAt
  const name = asString(row.name)
  const sample = row.sample === true
  const note = asString(row.note) || undefined
  const base = { handle, name, at, sample, note }

  if (kind === 'site') {
    const siteRow = asRecord(row.site) ?? row
    const site = siteFrom(siteRow, handle, name)
    if (!site) return null
    return {
      ...base,
      id: asString(row.id) || stamp('site', handle, at, site.url),
      kind: 'site',
      site,
    }
  }

  if (kind === 'listing_signal') {
    const signalRow = asRecord(row.listing_signal) ?? row
    const signal = asString(signalRow.signal || signalRow.snippet || signalRow.listing_signal)
    if (!signal) return null
    const listing: ListingSignal = {
      name: asString(signalRow.name) || name || undefined,
      handle: handleOf(signalRow) || handle,
      signal,
      prev: signalRow.prev === null || typeof signalRow.prev === 'string' ? (signalRow.prev as string | null) : undefined,
      keyword: asString(signalRow.keyword) || undefined,
      source: asString(signalRow.source) || undefined,
    }
    return {
      ...base,
      id: asString(row.id) || stamp('listing_signal', handle, '', signal.slice(0, 120)),
      kind: 'listing_signal',
      listing_signal: listing,
    }
  }

  if (kind === 'ca') {
    const parsed = normalizeCa(asRecord(row.ca) ? row.ca : row.ca ?? row)
    const flat = typeof row.ca === 'string' ? row.ca : ''
    const ca = flat || parsed?.ca || ''
    if (!ca) return null
    return {
      ...base,
      id: asString(row.id) || stamp('ca', handle, at, ca),
      kind: 'ca',
      ca,
      ca_chain: asString(row.ca_chain) || parsed?.ca_chain || null,
      ca_source: asString(row.ca_source) || parsed?.ca_source || null,
    }
  }

  const deployRow = asRecord(row.factory_deploy) ?? row
  const deploy: FactoryDeploy = {
    chain: asString(deployRow.chain) || undefined,
    tx: asString(deployRow.tx) || undefined,
    factory: asString(deployRow.factory) || undefined,
    token: asString(deployRow.token) || undefined,
    block: deployRow.block === null ? null : asNumber(deployRow.block),
    notes: asString(deployRow.notes) || undefined,
    name: name || undefined,
    handle,
  }
  if (!deploy.tx && !deploy.factory && !deploy.token && !deploy.notes) return null
  return {
    ...base,
    id: asString(row.id) || stamp('factory', handle, at, deploy.tx || deploy.factory || deploy.token || ''),
    kind: 'factory',
    factory_deploy: deploy,
  }
}

function ingestSiteRow(row: Record<string, unknown>, out: MonitorEvent[], fallbackAt: string) {
  const handle = handleOf(row)
  const url = asString(row.url)
  if (!handle || !url) return
  if (row.http_code == null && row.status == null && row.time_s == null && row.ok == null) return
  const at = asString(row.checked_at) || fallbackAt
  const name = asString(row.name)
  const site = siteFrom(row, handle, name)
  if (!site) return
  push(out, {
    id: stamp('site', handle, at, url),
    kind: 'site',
    at,
    handle,
    name,
    site,
  })
}

function ingestResult(row: Record<string, unknown>, out: MonitorEvent[], fallbackAt: string) {
  const at = asString(row.checked_at) || fallbackAt
  ingestSiteRow(row, out, at)
  const handle = handleOf(row)
  const name = asString(row.name)

  if (Array.isArray(row.sites)) {
    for (const site of row.sites) {
      const probe = asRecord(site)
      if (!probe || !handle) continue
      const siteProbe = siteFrom(probe, handle, name)
      if (!siteProbe) continue
      push(out, {
        id: stamp('site', handle, at, siteProbe.url),
        kind: 'site',
        at,
        handle,
        name,
        site: siteProbe,
      })
    }
  }

  const listingSignal = asString(row.listing_signal)
  if (handle && listingSignal) {
    push(out, {
      id: stamp('listing_signal', handle, '', listingSignal.slice(0, 120)),
      kind: 'listing_signal',
      at,
      handle,
      name,
      listing_signal: { name, handle, signal: listingSignal, prev: null },
    })
  }

  if (Array.isArray(row.signals)) {
    for (const item of row.signals) {
      const signal = asRecord(item)
      if (!signal || !handle) continue
      const text = asString(signal.snippet || signal.signal)
      if (!text) continue
      push(out, {
        id: stamp('listing_signal', handle, '', text.slice(0, 120)),
        kind: 'listing_signal',
        at,
        handle,
        name,
        listing_signal: {
          name,
          handle,
          signal: text,
          prev: null,
          keyword: asString(signal.keyword) || undefined,
          source: asString(signal.source) || undefined,
        },
      })
    }
  }

  if (Array.isArray(row.cas)) {
    for (const item of row.cas) ingestCaItem(item, handle, name, at, out)
  }
  if (row.primary_ca) ingestCaItem(row.primary_ca, handle, name, at, out, row)
}

function ingestCaItem(
  item: unknown,
  handle: string,
  name: string,
  at: string,
  out: MonitorEvent[],
  extra?: Record<string, unknown>,
) {
  const parsed = normalizeCa(item)
  if (!parsed || !handle) return
  const caChain = parsed.ca_chain || asString(extra?.ca_chain)
  const caSource = parsed.ca_source || asString(extra?.ca_source)
  push(out, {
    id: stamp('ca', handle, '', parsed.ca),
    kind: 'ca',
    at,
    handle,
    name: name || asString(extra?.name),
    ca: parsed.ca,
    ca_chain: caChain || null,
    ca_source: caSource || null,
  })
}

function ingestWatchProject(row: Record<string, unknown>, out: MonitorEvent[], fallbackAt: string) {
  const handle = handleOf(row)
  if (!handle) return
  const at = asString(row.last_checked || row.locked_at) || fallbackAt
  const name = asString(row.name)
  if (typeof row.ca === 'string' && row.ca.trim()) {
    ingestCaItem(row.ca, handle, name, at, out, row)
  }
  const signal = asString(row.listing_signal)
  if (signal) {
    push(out, {
      id: stamp('listing_signal', handle, '', signal.slice(0, 120)),
      kind: 'listing_signal',
      at,
      handle,
      name,
      listing_signal: { name, handle, signal, prev: null },
    })
  }
}

function ingestFactory(row: Record<string, unknown>, out: MonitorEvent[], fallbackAt: string) {
  const event = eventFromNormalized({ ...row, kind: row.kind || 'factory' }, fallbackAt)
  if (event?.kind === 'factory') push(out, event)
}

function ingest(data: unknown, out: MonitorEvent[], fallbackAt: string) {
  if (Array.isArray(data)) {
    for (const item of data) ingest(item, out, fallbackAt)
    return
  }
  const obj = asRecord(data)
  if (!obj) return
  const at =
    asString(obj.checked_at_iso || obj.generated_at || obj.generated_at_utc || obj.locked_at || obj.checked_at) ||
    fallbackAt

  if (Array.isArray(obj.events)) {
    for (const item of obj.events) {
      const row = asRecord(item)
      if (!row) continue
      push(out, eventFromNormalized(row, at))
    }
  }
  if (obj.latest) ingest(obj.latest, out, at)
  if (obj.listing_scan) ingest(obj.listing_scan, out, at)
  if (obj.watchlist) ingest(obj.watchlist, out, at)

  if (Array.isArray(obj.results)) {
    for (const item of obj.results) {
      const row = asRecord(item)
      if (row) ingestResult(row, out, at)
    }
  }
  if (Array.isArray(obj.new_listing_signals)) {
    for (const item of obj.new_listing_signals) {
      const row = asRecord(item)
      if (!row) continue
      const signal = asString(row.signal)
      const handle = handleOf(row)
      if (!handle || !signal) continue
      push(out, {
        id: stamp('listing_signal', handle, '', signal.slice(0, 120)),
        kind: 'listing_signal',
        at: asString(row.checked_at) || at,
        handle,
        name: asString(row.name),
        listing_signal: {
          name: asString(row.name) || undefined,
          handle,
          signal,
          prev: row.prev === null || typeof row.prev === 'string' ? (row.prev as string | null) : null,
        },
      })
    }
  }
  if (Array.isArray(obj.new_cas)) {
    for (const item of obj.new_cas) {
      const row = asRecord(item)
      ingestCaItem(item, row ? handleOf(row) : '', row ? asString(row.name) : '', at, out, row ?? undefined)
    }
  }
  if (Array.isArray(obj.projects)) {
    for (const item of obj.projects) {
      const row = asRecord(item)
      if (row) ingestWatchProject(row, out, at)
    }
  }
  if (Array.isArray(obj.factory_deploys)) {
    for (const item of obj.factory_deploys) {
      const row = asRecord(item)
      if (row) ingestFactory(row, out, at)
    }
  }
}

function dedupe(events: MonitorEvent[]): MonitorEvent[] {
  const seen = new Set<string>()
  const out: MonitorEvent[] = []
  for (const event of events) {
    const key =
      event.kind === 'listing_signal'
        ? `sig|${event.handle.toLowerCase()}|${event.listing_signal?.signal ?? ''}`
        : event.kind === 'ca'
          ? `ca|${event.handle.toLowerCase()}|${event.ca ?? ''}`
          : event.kind === 'site'
            ? `site|${event.handle.toLowerCase()}|${event.site?.url ?? ''}|${event.at}|${event.site?.status ?? ''}|${event.site?.time_s ?? ''}`
            : event.id
    if (seen.has(key)) continue
    seen.add(key)
    out.push(event)
  }
  return out
}

export function listedMonitorFiles(data: unknown): string[] {
  const obj = asRecord(data)
  if (!obj || !Array.isArray(obj.files)) return []
  return obj.files.filter((file): file is string => {
    if (typeof file !== 'string') return false
    const trimmed = file.trim()
    return Boolean(trimmed) && !trimmed.includes('..') && !trimmed.startsWith('/') && !trimmed.includes('://')
  })
}

export function collectMonitorEvents(data: unknown): MonitorEvent[] {
  const out: MonitorEvent[] = []
  ingest(data, out, '')
  return dedupe(out)
}

export function readMonitorDocument(data: unknown): MonitorDocument {
  const obj = asRecord(data)
  return {
    events: collectMonitorEvents(data),
    generatedAt: obj ? asString(obj.generated_at || obj.generated_at_utc || obj.checked_at_iso) || undefined : undefined,
    note: obj ? asString(obj.note) || undefined : undefined,
    files: listedMonitorFiles(data),
  }
}

export function eventsForHandle(events: MonitorEvent[], handle: string): MonitorEvent[] {
  const key = handle.replace(/^@/, '').trim().toLowerCase()
  return events
    .filter((event) => event.handle.replace(/^@/, '').toLowerCase() === key)
    .sort((a, b) => (Date.parse(b.at) || 0) - (Date.parse(a.at) || 0) || a.kind.localeCompare(b.kind))
}

export type SiteHealth = 'up' | 'down' | 'unknown'

export function siteHealth(site?: SiteProbe): SiteHealth {
  if (!site) return 'unknown'
  const status = (site.status || '').toLowerCase()
  if (status === 'up' || status === 'ok') return 'up'
  if (status === 'down' || status === 'error' || status === 'fail') return 'down'
  if (site.ok === true) return 'up'
  if (site.ok === false) return 'down'
  const code = Number(site.http_code)
  if (Number.isFinite(code) && code >= 200 && code < 400) return 'up'
  if (Number.isFinite(code) && code >= 400) return 'down'
  return 'unknown'
}

export interface MonitorSnapshot {
  ca?: string
  caChain?: string
  caSource?: string
  caAt?: string
  lastSite?: {
    status: SiteHealth
    rawStatus?: string
    url: string
    timeS?: number
    httpCode?: string
    error?: string
    at: string
  }
  lastSignal?: {
    text: string
    at: string
    prev?: string | null
  }
  lastFactory?: {
    at: string
    chain?: string
    token?: string
    factory?: string
    tx?: string
    notes?: string
  }
}

export function summarizeEvents(events: MonitorEvent[]): MonitorSnapshot {
  const sorted = events
    .filter((event) => !event.sample)
    .sort((a, b) => (Date.parse(b.at) || 0) - (Date.parse(a.at) || 0))
  const snap: MonitorSnapshot = {}
  for (const event of sorted) {
    if (!snap.lastSite && event.kind === 'site' && event.site) {
      snap.lastSite = {
        status: siteHealth(event.site),
        rawStatus: event.site.status,
        url: event.site.url,
        timeS: event.site.time_s,
        httpCode: event.site.http_code != null ? String(event.site.http_code) : undefined,
        error: event.site.error,
        at: event.at,
      }
    }
    if (!snap.lastSignal && event.kind === 'listing_signal' && event.listing_signal?.signal) {
      snap.lastSignal = {
        text: event.listing_signal.signal,
        at: event.at,
        prev: event.listing_signal.prev,
      }
    }
    if (!snap.ca && event.kind === 'ca' && event.ca) {
      snap.ca = event.ca
      snap.caChain = event.ca_chain || undefined
      snap.caSource = event.ca_source || undefined
      snap.caAt = event.at
    }
    if (!snap.lastFactory && event.kind === 'factory' && event.factory_deploy) {
      snap.lastFactory = {
        at: event.at,
        chain: event.factory_deploy.chain,
        token: event.factory_deploy.token,
        factory: event.factory_deploy.factory,
        tx: event.factory_deploy.tx,
        notes: event.factory_deploy.notes,
      }
    }
  }
  return snap
}

export function snapshotForCandidate(candidate: Candidate, events: MonitorEvent[]): MonitorSnapshot {
  const snap = summarizeEvents(eventsForHandle(events, candidate.handle))
  if (!snap.ca && candidate.ca) {
    snap.ca = candidate.ca
    snap.caChain = candidate.ca_chain || undefined
    snap.caSource = candidate.ca_source || undefined
  }
  if (!snap.lastSignal && candidate.listing_signal) {
    snap.lastSignal = {
      text: candidate.listing_signal,
      at: candidate.last_checked || candidate.date_iso || '',
    }
  }
  return snap
}
