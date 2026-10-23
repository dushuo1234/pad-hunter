import type { Candidate } from '../types'
import { pushNotice } from './notices'
import { resolvePushDate } from './pushDate'

const EMPTY: Candidate[] = []
const TEXT_KEYS = ['name', 'why', 'bio', 'chain', 'status', 'listing', 'tweet_url', 'category', 'source', 'notes', 'risk', 'ca', 'ca_chain', 'ca_source', 'listing_signal'] as const

let overlay: Candidate[] = EMPTY
const listeners = new Set<() => void>()

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

export function radarHandleKey(handle: string | null | undefined): string {
  return (handle ?? '').replace(/^@/, '').trim().toLowerCase()
}

function blank(value: unknown): boolean {
  if (value == null) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

/** Newer Telegram push. `pushed_at` wins over an older card `date_iso`. */
export function radarRecency(card: Candidate): [number, number] {
  const row = card as unknown as Record<string, unknown>
  let ms = 0
  for (const key of ['pushed_at', '_pushed_at', 'date_iso', 'updated_at']) {
    const value = row[key]
    if (typeof value !== 'string' && typeof value !== 'number') continue
    const parsed = Date.parse(String(value))
    if (Number.isFinite(parsed) && parsed > ms) ms = parsed
  }
  const message = typeof card.message_id === 'number' && Number.isFinite(card.message_id) ? card.message_id : 0
  return [ms, message]
}

function newer(left: Candidate, right: Candidate): boolean {
  const a = radarRecency(left)
  const b = radarRecency(right)
  if (a[0] !== b[0]) return a[0] > b[0]
  return a[1] >= b[1]
}

function preservePushDate(prev: Candidate, next: Candidate): Candidate {
  const prevStamp = resolvePushDate([prev])
  const nextStamp = resolvePushDate([next])
  if (!prevStamp) return next
  if (!nextStamp || Date.parse(prevStamp.at) < Date.parse(nextStamp.at)) {
    return { ...next, push_date: prev.push_date || prevStamp.at }
  }
  return next
}

function mergeOne(prev: Candidate | undefined, next: Candidate): Candidate {
  if (!prev) return next
  if (!newer(next, prev)) return prev
  const merged: Candidate = { ...prev, ...next }
  const prevRow = prev as unknown as Record<string, unknown>
  const nextRow = next as unknown as Record<string, unknown>
  const out = merged as unknown as Record<string, unknown>
  for (const key of TEXT_KEYS) {
    if (blank(nextRow[key]) && !blank(prevRow[key])) out[key] = prevRow[key]
  }
  if ((!next.followers || next.followers === 0 || next.followers === '0') && prev.followers) merged.followers = prev.followers
  if (!next.kol_followers && prev.kol_followers) merged.kol_followers = prev.kol_followers
  if (!next.score && prev.score) merged.score = prev.score
  if (next.listing_at == null && prev.listing_at) merged.listing_at = prev.listing_at
  if (next.launch_at == null && prev.launch_at) merged.launch_at = prev.launch_at
  if ((!next.sites || next.sites.length === 0) && prev.sites && prev.sites.length > 0) merged.sites = prev.sites
  return preservePushDate(prev, merged)
}

/** Upsert by lowercase handle. The newer push replaces the older card. */
export function mergeRadarCards(base: readonly Candidate[], incoming: readonly Candidate[]): Candidate[] {
  if (incoming.length === 0) return [...base]
  const map = new Map<string, Candidate>()
  const order: string[] = []
  const place = (card: Candidate) => {
    const key = radarHandleKey(card.handle)
    if (!key) return
    if (!map.has(key)) order.push(key)
    map.set(key, mergeOne(map.get(key), { ...card, handle: card.handle.replace(/^@/, '').trim() || card.handle }))
  }
  for (const card of base) place(card)
  for (const card of incoming) place(card)
  return order.map((key) => map.get(key)).filter((card): card is Candidate => Boolean(card))
}

function sitesFrom(row: Record<string, unknown>): string[] | undefined {
  const found: string[] = []
  if (Array.isArray(row.sites)) {
    for (const site of row.sites) {
      const text = asString(site)
      if (text) found.push(text)
    }
  } else if (typeof row.sites === 'string' && row.sites.trim()) found.push(row.sites.trim())
  const site = asString(row.site)
  if (site) found.push(site)
  return found.length > 0 ? [...new Set(found)] : undefined
}

/** Worker radar cards use the candidate shape, plus `pushed_at` and a single `site`. */
export function coerceRadarCard(raw: unknown): Candidate | null {
  const row = asRecord(raw)
  if (!row) return null
  const handle = asString(row.handle).replace(/^@/, '')
  if (!handle) return null
  const name = asString(row.name) || handle
  const pushed = asString(row.pushed_at || row._pushed_at)
  const dateIso = asString(row.date_iso || row.dateIso) || pushed
  const pushDate = asString(row.push_date || row.pushDate)
  const rank = typeof row.rank === 'number' && Number.isFinite(row.rank) ? row.rank : 10_000
  const followers = typeof row.followers === 'number' || typeof row.followers === 'string' ? row.followers : 0
  const kol = typeof row.kol_followers === 'number' && Number.isFinite(row.kol_followers) ? row.kol_followers : 0
  const score = typeof row.score === 'number' && Number.isFinite(row.score) ? row.score : 0
  const card: Candidate = {
    rank,
    handle,
    name,
    followers,
    kol_followers: kol,
    bio: asString(row.bio),
    why: asString(row.why),
    score,
    tweet_url: asString(row.tweet_url || row.tweetUrl),
    chain: asString(row.chain),
  }
  if (dateIso) card.date_iso = dateIso
  if (pushDate) card.push_date = pushDate
  const status = asString(row.status)
  if (status) card.status = status
  const listing = asString(row.listing)
  if (listing) card.listing = listing
  const category = asString(row.category)
  if (category) card.category = category
  const source = asString(row.source)
  if (source) card.source = source
  const notes = asString(row.notes)
  if (notes) card.notes = notes
  const sites = sitesFrom(row)
  if (sites) card.sites = sites
  const listingAt = asString(row.listing_at || row.listingAt)
  if (listingAt) card.listing_at = listingAt
  const message = row.message_id
  if (typeof message === 'number' && Number.isFinite(message)) card.message_id = message
  if (pushed) (card as Candidate & { pushed_at?: string }).pushed_at = pushed
  return card
}

export function readRadarCards(data: unknown): Candidate[] {
  if (Array.isArray(data)) return mergeRadarCards([], data.map(coerceRadarCard).filter((card): card is Candidate => Boolean(card)))
  const row = asRecord(data)
  if (!row) return []
  const state = asRecord(row.state)
  const list = Array.isArray(row.cards)
    ? row.cards
    : Array.isArray(row.candidates)
      ? row.candidates
      : state && Array.isArray(state.cards)
        ? state.cards
        : null
  if (!list) return []
  return mergeRadarCards([], list.map(coerceRadarCard).filter((card): card is Candidate => Boolean(card)))
}

function fingerprint(cards: readonly Candidate[]): string {
  return cards
    .map((card) => `${radarHandleKey(card.handle)}|${card.name}|${card.date_iso ?? ''}|${card.push_date ?? ''}|${card.status ?? ''}|${card.listing ?? ''}`)
    .join('\n')
}

function publish(next: Candidate[]) {
  if (fingerprint(overlay) === fingerprint(next)) return
  overlay = next.length > 0 ? next : EMPTY
  for (const listener of listeners) listener()
}

function announce(cards: Candidate[], previous: ReadonlySet<string>) {
  const fresh = cards.filter((card) => !previous.has(radarHandleKey(card.handle)))
  if (fresh.length === 0) return
  const label = fresh.length === 1 ? fresh[0]?.name || fresh[0]?.handle || '项目' : `${fresh.length} 个项目`
  pushNotice(`新推送 ${label}`)
}

export function getRadarOverlay(): Candidate[] {
  return overlay
}

export function getServerRadarOverlay(): Candidate[] {
  return EMPTY
}

export function subscribeRadar(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function applyRadarSnapshot(raw: unknown[], opts?: { announce?: boolean }): void {
  const cards = readRadarCards(raw)
  const previous = new Set(overlay.map((card) => radarHandleKey(card.handle)))
  publish(cards)
  if (opts?.announce) announce(cards, previous)
}

/** Drop live TG cards for handles that just moved to 已开盘. */
export function forgetRadarHandles(handles: readonly string[]): void {
  const drop = new Set(handles.map((handle) => radarHandleKey(handle)).filter(Boolean))
  if (drop.size === 0 || overlay.length === 0) return
  publish(overlay.filter((card) => !drop.has(radarHandleKey(card.handle))))
}

export function applyRadarDelta(raw: unknown[]): void {
  const cards = readRadarCards(raw)
  if (cards.length === 0) return
  const previous = new Set(overlay.map((card) => radarHandleKey(card.handle)))
  publish(mergeRadarCards(overlay, cards))
  announce(cards, previous)
}
