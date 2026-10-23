/**
 * Pure helpers for the workbench realtime socket.
 * The browser client lives in boardSync; these functions stay free of WebSocket
 * so message handling can be tested without a server.
 */

import { parsePinResponse, parseReviewResponse, type PinMergeState, type ReviewWire } from './syncMerge.ts'

export const SOCKET_AUTH_CLOSE = 4401
/** Worker restarted. Reconnect on a short backoff instead of the normal 1s series. */
export const SOCKET_REDEPLOY_CLOSE = 1012

export type SocketEvent =
  | { kind: 'hello'; version: string; serverTime: string; launched: unknown; blocklist: unknown }
  | { kind: 'pins'; state: PinMergeState; originClientId: string }
  | { kind: 'reviewed'; marks: Record<string, ReviewWire>; originClientId: string }
  | { kind: 'radar'; cards: unknown[]; syncedAt: string; originClientId: string; event: string }
  | { kind: 'radar_delta'; cards: unknown[]; originClientId: string }
  | { kind: 'launched_mark'; payload: unknown; originClientId: string }
  | { kind: 'launched_unmark'; handle: string; originClientId: string }
  | { kind: 'blocklist'; payload: unknown; originClientId: string }
  | { kind: 'ping' }
  | { kind: 'ignore' }

export function isSocketAuthClose(code: number): boolean {
  return code === SOCKET_AUTH_CLOSE
}

export function isSocketRedeployClose(code: number): boolean {
  return code === SOCKET_REDEPLOY_CLOSE
}

/** 1s, 2s, 4s… capped at 30s, plus up to 20% jitter. */
export function wsBackoffMs(attempt: number, random = Math.random()): number {
  return backoffMs(1000, attempt, random)
}

/** After close 1012: 500ms, 1s, 2s… capped at 30s, plus up to 20% jitter. */
export function wsRedeployBackoffMs(attempt: number, random = Math.random()): number {
  return backoffMs(500, attempt, random)
}

function backoffMs(start: number, attempt: number, random: number): number {
  const step = Math.max(0, Math.floor(attempt))
  const base = Math.min(30_000, start * 2 ** step)
  const jitter = Math.min(1, Math.max(0, random))
  return Math.min(30_000, Math.round(base * (1 + jitter * 0.2)))
}

export function workbenchWsUrl(httpBase: string, token: string): string {
  const url = new URL(httpBase)
  if (url.protocol === 'https:') url.protocol = 'wss:'
  else if (url.protocol === 'http:') url.protocol = 'ws:'
  else throw new Error('接口地址需要是 http(s) URL')
  const prefix = url.pathname.replace(/\/+$/, '')
  url.pathname = `${prefix}/v1/workbench/ws`
  url.search = ''
  url.hash = ''
  url.searchParams.set('token', token)
  return url.toString()
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  return value as Record<string, unknown>
}

function asString(value: unknown): string {
  if (typeof value === 'string') return value.trim()
  if (typeof value === 'number' && Number.isFinite(value)) return String(value)
  return ''
}

export function parseSocketMessage(raw: unknown): SocketEvent {
  let data = raw
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return { kind: 'ignore' }
    try {
      data = JSON.parse(text) as unknown
    } catch {
      return { kind: 'ignore' }
    }
  }
  const row = asRecord(data)
  if (!row) return { kind: 'ignore' }
  const type = asString(row.type).toLowerCase()
  if (type === 'ping') return { kind: 'ping' }
  if (type === 'hello') {
    return {
      kind: 'hello',
      version: asString(row.version),
      serverTime: asString(row.server_time || row.serverTime),
      launched: row.launched,
      blocklist: row.blocklist,
    }
  }
  const originClientId = asString(row.origin_client_id || row.originClientId)
  if (type === 'radar') {
    const state = asRecord(row.state) ?? row
    const cards = Array.isArray(state.cards) ? state.cards : Array.isArray(row.cards) ? row.cards : null
    if (!cards) return { kind: 'ignore' }
    return {
      kind: 'radar',
      cards,
      syncedAt: asString(state.synced_at || state.syncedAt),
      originClientId,
      event: asString(row.event),
    }
  }
  if (type === 'radar_delta') {
    const cards = Array.isArray(row.cards) ? row.cards : null
    if (!cards) return { kind: 'ignore' }
    return { kind: 'radar_delta', cards, originClientId }
  }
  if (type === 'launched_mark' || type === 'launched') {
    return { kind: 'launched_mark', payload: row.state ?? row, originClientId }
  }
  if (type === 'launched_unmark') {
    const state = asRecord(row.state)
    const handle = asString(row.handle || state?.handle)
    if (!handle) return { kind: 'ignore' }
    return { kind: 'launched_unmark', handle, originClientId }
  }
  if (type === 'blocklist') {
    return { kind: 'blocklist', payload: row.state ?? row, originClientId }
  }
  if (type === 'pins') {
    const parsed = parsePinResponse(row.state)
    if (!parsed) return { kind: 'ignore' }
    return { kind: 'pins', state: parsed.state, originClientId }
  }
  if (type === 'reviewed') {
    const parsed = parseReviewResponse(row.state)
    if (!parsed) return { kind: 'ignore' }
    return { kind: 'reviewed', marks: parsed.marks, originClientId }
  }
  return { kind: 'ignore' }
}

export function pinsSyncFrame(clientId: string, state: PinMergeState): { type: 'pins_sync'; body: { client_id: string; items: PinMergeState['items']; removed: PinMergeState['removed'] } } {
  return {
    type: 'pins_sync',
    body: { client_id: clientId, items: state.items, removed: state.removed },
  }
}

export function reviewedSyncFrame(clientId: string, marks: Record<string, ReviewWire>): { type: 'reviewed_sync'; body: { client_id: string; marks: Record<string, ReviewWire> } } {
  return { type: 'reviewed_sync', body: { client_id: clientId, marks } }
}

export function pongFrame(): { type: 'pong' } {
  return { type: 'pong' }
}
