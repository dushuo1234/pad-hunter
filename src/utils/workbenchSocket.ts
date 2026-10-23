/**
 * Pure helpers for the workbench realtime socket.
 * The browser client lives in boardSync; these functions stay free of WebSocket
 * so message handling can be tested without a server.
 */

import { parsePinResponse, parseReviewResponse, type PinMergeState, type ReviewWire } from './syncMerge.ts'

export const SOCKET_AUTH_CLOSE = 4401

export type SocketEvent =
  | { kind: 'hello'; version: string; serverTime: string }
  | { kind: 'pins'; state: PinMergeState; originClientId: string }
  | { kind: 'reviewed'; marks: Record<string, ReviewWire>; originClientId: string }
  | { kind: 'ping' }
  | { kind: 'ignore' }

export function isSocketAuthClose(code: number): boolean {
  return code === SOCKET_AUTH_CLOSE
}

/** 1s, 2s, 4s… capped at 30s, plus up to 20% jitter. */
export function wsBackoffMs(attempt: number, random = Math.random()): number {
  const step = Math.max(0, Math.floor(attempt))
  const base = Math.min(30_000, 1000 * 2 ** step)
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
    return { kind: 'hello', version: asString(row.version), serverTime: asString(row.server_time || row.serverTime) }
  }
  const originClientId = asString(row.origin_client_id || row.originClientId)
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
