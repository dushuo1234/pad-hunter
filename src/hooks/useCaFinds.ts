import { useMemo, useState, useSyncExternalStore } from 'react'
import type { CaFind } from '../types'
import { CA_FINDS_URL, caFindKey, parseCaFinds } from '../utils/caFinds'

const POLL_MS = 1000
const EMPTY_FRESH: Set<string> = new Set()

export interface CaFindsState {
  finds: CaFind[]
  generatedAt?: string
  lastChecked: string | null
  loading: boolean
  error: string | null
  freshKeys: Set<string>
}

interface CaFindsSnapshot {
  finds: CaFind[]
  generatedAt?: string
  lastChecked: string | null
  loading: boolean
  error: string | null
  /** True after the first successful read. Errors before that leave this false. */
  ready: boolean
}

let snapshot: CaFindsSnapshot = {
  finds: [],
  generatedAt: undefined,
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
    const keys = payload.finds.map(caFindKey)
    const nextSignature = `${payload.generated_at ?? ''}\n${keys.join('\n')}`
    if (nextSignature !== signature) {
      signature = nextSignature
      publish({
        finds: payload.finds,
        generatedAt: payload.generated_at,
        lastChecked: new Date().toISOString(),
        loading: false,
        error: null,
        ready: true,
      })
    } else {
      publish({
        ...snapshot,
        finds: snapshot.finds,
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
    setBaseline(new Set(data.finds.map(caFindKey)))
  }
  const freshKeys = useMemo(() => {
    if (!baseline) return EMPTY_FRESH
    let fresh: Set<string> | null = null
    for (const find of data.finds) {
      const key = caFindKey(find)
      if (baseline.has(key)) continue
      if (!fresh) fresh = new Set()
      fresh.add(key)
    }
    return fresh ?? EMPTY_FRESH
  }, [baseline, data.finds])

  return {
    finds: data.finds,
    generatedAt: data.generatedAt,
    lastChecked: data.lastChecked,
    loading: data.loading,
    error: data.error,
    freshKeys,
  }
}
