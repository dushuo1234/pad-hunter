import { useMemo, useState, useSyncExternalStore } from 'react'
import type { CaFind, CaFindsPayload, CaProjectLock, CaStatusCounts } from '../types'
import { CA_FINDS_URL, caFindKey, EMPTY_STATUS_COUNTS, parseCaFinds } from '../utils/caFinds'

const POLL_MS = 1000
const EMPTY_FRESH: Set<string> = new Set()
const EMPTY_FINDS: CaFind[] = []
const EMPTY_LOCKS: CaProjectLock[] = []

export interface CaFindsState {
  finds: CaFind[]
  suspectedCopycats: CaFind[]
  supersededArchive: CaFind[]
  launchedHistory: CaFind[]
  walletActivity: CaFind[]
  locks: CaProjectLock[]
  generatedAt?: string
  schemaVersion?: number
  confidenceModel?: string
  statusCounts: CaStatusCounts
  suspectedCopycatCount: number
  lastChecked: string | null
  loading: boolean
  error: string | null
  freshKeys: Set<string>
}

interface CaFindsSnapshot {
  payload: CaFindsPayload
  lastChecked: string | null
  loading: boolean
  error: string | null
  /** True after the first successful read. Errors before that leave this false. */
  ready: boolean
}

const EMPTY_PAYLOAD: CaFindsPayload = {
  statusCounts: EMPTY_STATUS_COUNTS,
  confirmedCount: 0,
  candidateCount: 0,
  suspectedCopycatCount: 0,
  finds: EMPTY_FINDS,
  suspectedCopycats: EMPTY_FINDS,
  supersededArchive: EMPTY_FINDS,
  launchedHistory: EMPTY_FINDS,
  walletActivity: EMPTY_FINDS,
  locks: EMPTY_LOCKS,
}

let snapshot: CaFindsSnapshot = {
  payload: EMPTY_PAYLOAD,
  lastChecked: null,
  loading: true,
  error: null,
  ready: false,
}

const listeners = new Set<() => void>()
let subscribers = 0
let timer = 0
let inflight = false
let signature = ''

function emit() {
  for (const listener of listeners) listener()
}

function publish(next: CaFindsSnapshot) {
  snapshot = next
  emit()
}

async function tick() {
  if (inflight) return
  inflight = true
  try {
    const res = await fetch(`${CA_FINDS_URL}?t=${Date.now()}`, { cache: 'no-store' })
    if (!res.ok) throw new Error(`加载失败 (${res.status})`)
    const payload = parseCaFinds(await res.json())
    const keys = [
      ...payload.finds,
      ...payload.suspectedCopycats,
      ...payload.supersededArchive,
      ...payload.launchedHistory,
      ...payload.walletActivity,
    ].map(caFindKey)
    const lockSig = payload.locks.map((lock) => `${lock.id}\n${lock.url}`).join('\n')
    const counts = payload.statusCounts
    const nextSignature = [
      payload.generated_at ?? '',
      payload.schemaVersion ?? '',
      counts.confirmed,
      counts.candidate,
      counts.superseded,
      counts.not_ca,
      payload.suspectedCopycatCount,
      lockSig,
      keys.join('\n'),
    ].join('\n')
    if (nextSignature !== signature) {
      signature = nextSignature
      publish({
        payload,
        lastChecked: new Date().toISOString(),
        loading: false,
        error: null,
        ready: true,
      })
    } else {
      publish({
        ...snapshot,
        payload: snapshot.payload,
        lastChecked: new Date().toISOString(),
        loading: false,
        error: null,
        ready: true,
      })
    }
  } catch (reason) {
    publish({
      ...snapshot,
      lastChecked: new Date().toISOString(),
      loading: false,
      error: reason instanceof Error ? reason.message : '加载失败',
    })
  } finally {
    inflight = false
  }
}

function ensureStarted() {
  if (timer) return
  void tick()
  timer = window.setInterval(() => void tick(), POLL_MS)
}

function stopIfIdle() {
  if (subscribers > 0 || timer === 0) return
  window.clearInterval(timer)
  timer = 0
}

function subscribe(listener: () => void) {
  listeners.add(listener)
  subscribers += 1
  ensureStarted()
  return () => {
    listeners.delete(listener)
    subscribers -= 1
    stopIfIdle()
  }
}

function getSnapshot(): CaFindsSnapshot {
  return snapshot
}

/**
 * One shared poll of `ca_finds.json`. The 发现CA page and the app-level alert both subscribe.
 * "新" is still scoped to this hook instance, so it starts when the 发现CA page mounts.
 */
export function useCaFinds(): CaFindsState {
  const data = useSyncExternalStore(subscribe, getSnapshot, getSnapshot)
  const [baseline, setBaseline] = useState<Set<string> | null>(null)
  if (baseline == null && data.ready) {
    setBaseline(
      new Set(
        [
          ...data.payload.finds,
          ...data.payload.suspectedCopycats,
          ...data.payload.supersededArchive,
          ...data.payload.launchedHistory,
          ...data.payload.walletActivity,
        ].map(caFindKey),
      ),
    )
  }
  const rows = useMemo(
    () => [
      ...data.payload.finds,
      ...data.payload.suspectedCopycats,
      ...data.payload.supersededArchive,
      ...data.payload.launchedHistory,
      ...data.payload.walletActivity,
    ],
    [data.payload],
  )
  const freshKeys = useMemo(() => {
    if (!baseline) return EMPTY_FRESH
    let fresh: Set<string> | null = null
    for (const find of rows) {
      const key = caFindKey(find)
      if (baseline.has(key)) continue
      if (!fresh) fresh = new Set()
      fresh.add(key)
    }
    return fresh ?? EMPTY_FRESH
  }, [baseline, rows])

  return {
    finds: data.payload.finds,
    suspectedCopycats: data.payload.suspectedCopycats,
    supersededArchive: data.payload.supersededArchive,
    launchedHistory: data.payload.launchedHistory,
    walletActivity: data.payload.walletActivity,
    locks: data.payload.locks,
    generatedAt: data.payload.generated_at,
    schemaVersion: data.payload.schemaVersion,
    confidenceModel: data.payload.confidenceModel,
    statusCounts: data.payload.statusCounts,
    suspectedCopycatCount: data.payload.suspectedCopycatCount,
    lastChecked: data.lastChecked,
    loading: data.loading,
    error: data.error,
    freshKeys,
  }
}
