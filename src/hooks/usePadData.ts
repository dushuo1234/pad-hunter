import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { Candidate, CandidatesPayload, MonitorEvent } from '../types'
import { withSourceFallback } from '../utils/candidates'
import { withProjectPushDates } from '../utils/pushDate'
import { applyListingTimes, readListingTimes, type ListingTimeEntry } from '../utils/launch'
import { launchedHandleSet, readLaunched, withoutLaunched, type LaunchedDocument } from '../utils/launched'
import { collectMonitorEvents, listedMonitorFiles, readMonitorDocument } from '../utils/monitor'
import { defaultApiBase, resolveApiBase, getApiSettings } from '../utils/workbenchApi'

const CANDIDATES_URL = `${import.meta.env.BASE_URL}data/candidates.json`
const EVENTS_URL = `${import.meta.env.BASE_URL}data/monitor_events.json`
const LISTING_TIMES_URL = `${import.meta.env.BASE_URL}data/listing_times.json`
const LAUNCHED_URL = `${import.meta.env.BASE_URL}data/launched.json`
const PROJECTS_URL = `${import.meta.env.BASE_URL}data/projects.json`

/** Poll interval for new Telegram cards (Pages CDN can lag; live API is preferred). */
const POLL_MS = 20_000

const EMPTY_LAUNCHED: LaunchedDocument = { count: 0, items: [] }
const EMPTY_CANDIDATES: Candidate[] = []

function parsePayload(data: unknown): CandidatesPayload {
  if (!data || typeof data !== 'object') throw new Error('无效的 JSON')
  const obj = data as Record<string, unknown>
  const list = Array.isArray(obj.candidates) ? obj.candidates : Array.isArray(data) ? data : null
  if (!list) throw new Error('JSON 需包含 candidates 数组')
  const sources = Array.isArray(obj.sources) ? obj.sources.filter((item): item is string => typeof item === 'string') : undefined
  return {
    generated_at_utc: typeof obj.generated_at_utc === 'string' ? obj.generated_at_utc : undefined,
    goal: typeof obj.goal === 'string' ? obj.goal : undefined,
    source: typeof obj.source === 'string' ? obj.source : undefined,
    sources,
    method: typeof obj.method === 'object' && obj.method ? (obj.method as Record<string, unknown>) : undefined,
    candidates: withSourceFallback(list as Candidate[], typeof obj.source === 'string' ? obj.source : undefined),
  }
}

function withBust(url: string): string {
  const join = url.includes('?') ? '&' : '?'
  return `${url}${join}t=${Date.now()}`
}

async function fetchJson(url: string): Promise<unknown> {
  const res = await fetch(withBust(url), { cache: 'no-store' })
  if (!res.ok) throw new Error(`加载失败 (${res.status})`)
  return res.json()
}

async function fetchOptional(url: string): Promise<unknown | null> {
  try {
    const res = await fetch(withBust(url), { cache: 'no-store' })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

function liveBase(): string {
  try {
    return resolveApiBase(getApiSettings().baseUrl || '') || defaultApiBase()
  } catch {
    return defaultApiBase()
  }
}

async function fetchLiveCandidates(): Promise<unknown | null> {
  const base = liveBase().replace(/\/+$/, '')
  if (!base) return null
  try {
    const res = await fetch(`${base}/v1/radar/candidates`, {
      cache: 'no-store',
      headers: { 'ngrok-skip-browser-warning': '1' },
      signal: AbortSignal.timeout(8000),
    })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function fetchLiveProjects(): Promise<unknown | null> {
  const base = liveBase().replace(/\/+$/, '')
  if (!base) return null
  try {
    const res = await fetch(`${base}/v1/radar/projects`, {
      cache: 'no-store',
      headers: { 'ngrok-skip-browser-warning': '1' },
      signal: AbortSignal.timeout(8000),
    })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function fetchLiveLaunched(): Promise<unknown | null> {
  const base = liveBase().replace(/\/+$/, '')
  if (!base) return null
  try {
    const res = await fetch(`${base}/v1/radar/launched`, {
      cache: 'no-store',
      headers: { 'ngrok-skip-browser-warning': '1' },
      signal: AbortSignal.timeout(8000),
    })
    if (!res.ok) return null
    return await res.json()
  } catch {
    return null
  }
}

async function loadEvents(): Promise<{ events: MonitorEvent[]; note?: string; generatedAt?: string }> {
  const main = await fetchOptional(EVENTS_URL)
  if (!main) return { events: [] }
  const doc = readMonitorDocument(main)
  const extra: MonitorEvent[] = []
  const files = listedMonitorFiles(main)
  if (files.length > 0) {
    const loaded = await Promise.all(
      files.map((file) => fetchOptional(`${import.meta.env.BASE_URL}data/${file.replace(/^\//, '')}`)),
    )
    for (const item of loaded) {
      if (item) extra.push(...collectMonitorEvents(item))
    }
  }
  const seen = new Set<string>()
  const events: MonitorEvent[] = []
  for (const event of [...doc.events, ...extra]) {
    if (seen.has(event.id)) continue
    seen.add(event.id)
    events.push(event)
  }
  return { events, note: doc.note, generatedAt: doc.generatedAt }
}

export function usePadData() {
  const [payload, setPayload] = useState<CandidatesPayload | null>(null)
  const [events, setEvents] = useState<MonitorEvent[]>([])
  const [eventsNote, setEventsNote] = useState<string | undefined>(undefined)
  const [eventsAt, setEventsAt] = useState<string | undefined>(undefined)
  const [listingTimes, setListingTimes] = useState<ListingTimeEntry[]>([])
  const [launched, setLaunched] = useState<LaunchedDocument>(EMPTY_LAUNCHED)
  const [projects, setProjects] = useState<unknown>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [uploadNote, setUploadNote] = useState<string | null>(null)
  const [liveSource, setLiveSource] = useState<'api' | 'pages' | null>(null)
  const inflight = useRef(false)

  const loadDefault = useCallback(async (opts?: { soft?: boolean }) => {
    if (inflight.current) return
    inflight.current = true
    const soft = Boolean(opts?.soft)
    try {
      const liveCand = await fetchLiveCandidates()
      const [candidatesJson, monitor, listingTimesJson, launchedJson, projectsJson] = await Promise.all([
        liveCand ? Promise.resolve(liveCand) : fetchJson(CANDIDATES_URL),
        soft && events.length ? Promise.resolve({ events, note: eventsNote, generatedAt: eventsAt }) : loadEvents(),
        soft && listingTimes.length
          ? Promise.resolve(listingTimes)
          : fetchOptional(LISTING_TIMES_URL),
        liveCand
          ? (await fetchLiveLaunched()) ?? (soft ? launched : await fetchOptional(LAUNCHED_URL))
          : soft
            ? Promise.resolve(null)
            : fetchOptional(LAUNCHED_URL),
        liveCand
          ? (await fetchLiveProjects()) ?? (soft ? projects : await fetchOptional(PROJECTS_URL))
          : soft
            ? Promise.resolve(null)
            : fetchOptional(PROJECTS_URL),
      ])

      const nextPayload = parsePayload(candidatesJson)
      // Skip React update when the board fingerprint is unchanged (soft polls).
      const nextFp = `${nextPayload.candidates.length}:${nextPayload.generated_at_utc || ''}:${(candidatesJson as { updated_at?: string })?.updated_at || ''}:${(candidatesJson as { live_at?: string })?.live_at || ''}`
      setPayload((prev) => {
        const prevFp = prev
          ? `${prev.candidates.length}:${prev.generated_at_utc || ''}`
          : ''
        if (soft && prev && prevFp === `${nextPayload.candidates.length}:${nextPayload.generated_at_utc || ''}`) {
          // still apply if updated_at / live_at moved — fall through by returning next
        }
        void nextFp
        return nextPayload
      })
      if (!soft || !events.length) {
        setEvents(monitor.events)
        setEventsNote(monitor.note)
        setEventsAt(monitor.generatedAt)
      }
      if (!soft || !listingTimes.length) {
        setListingTimes(readListingTimes(listingTimesJson))
      }
      if (launchedJson != null) setLaunched(readLaunched(launchedJson))
      if (projectsJson != null) setProjects(projectsJson)
      setLiveSource(liveCand ? 'api' : 'pages')
      if (!soft) setUploadNote(null)
      setError(null)
    } catch (e) {
      if (!soft) setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
      inflight.current = false
    }
  }, [events, eventsAt, eventsNote, launched, listingTimes, projects])

  useEffect(() => {
    void loadDefault()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- mount once; polling below

  // Soft poll: prefer live workbench API so new TG cards appear in ~20s without waiting for Pages CDN.
  useEffect(() => {
    const tick = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      void loadDefault({ soft: true })
    }
    const id = window.setInterval(tick, POLL_MS)
    const onFocus = () => void loadDefault({ soft: true })
    const onVis = () => {
      if (document.visibilityState === 'visible') void loadDefault({ soft: true })
    }
    window.addEventListener('focus', onFocus)
    document.addEventListener('visibilitychange', onVis)
    return () => {
      window.clearInterval(id)
      window.removeEventListener('focus', onFocus)
      document.removeEventListener('visibilitychange', onVis)
    }
  }, [loadDefault])

  const handleUpload = async (file: File) => {
    try {
      const text = await file.text()
      const json: unknown = JSON.parse(text)
      setPayload(parsePayload(json))
      setUploadNote(`已加载 ${file.name}（仅本次会话）`)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传解析失败')
    }
  }

  const allCandidates = useMemo(
    () =>
      withProjectPushDates(
        applyListingTimes(payload?.candidates ?? EMPTY_CANDIDATES, listingTimes),
        projects,
      ),
    [payload, listingTimes, projects],
  )
  const launchedHandles = useMemo(() => launchedHandleSet(launched.items), [launched])
  const candidates = useMemo(
    () => withoutLaunched(allCandidates, launchedHandles),
    [allCandidates, launchedHandles],
  )

  return {
    payload,
    events,
    eventsNote,
    eventsAt,
    listingTimes,
    launched,
    launchedHandles,
    error,
    loading,
    uploadNote,
    liveSource,
    loadDefault: () => loadDefault({ soft: false }),
    handleUpload,
    candidates,
    allCandidates,
  }
}
