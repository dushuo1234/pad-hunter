import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { Candidate, CandidatesPayload, MonitorEvent } from '../types'
import { isWorkbenchSocketOpen, subscribeBoardSync } from '../utils/boardSync'
import { findByHandle, withSourceFallback } from '../utils/candidates'
import { getBlockSnapshot, getServerBlockSnapshot, subscribeBlocklist, withManualLaunched } from '../utils/launchedMark'
import { withProjectPushDates } from '../utils/pushDate'
import { applyListingTimes, readListingTimes, type ListingTimeEntry } from '../utils/launch'
import { launchedHandleSet, readLaunched, sortLaunchedItems, withoutLaunched, type LaunchedDocument } from '../utils/launched'
import { collectMonitorEvents, listedMonitorFiles, readMonitorDocument } from '../utils/monitor'
import { getRadarOverlay, getServerRadarOverlay, mergeRadarCards, readRadarCards, subscribeRadar } from '../utils/radarLive'
import { defaultApiBase, fetchRadarRecent, resolveApiBase, getApiSettings } from '../utils/workbenchApi'

const CANDIDATES_URL = `${import.meta.env.BASE_URL}data/candidates.json`
const EVENTS_URL = `${import.meta.env.BASE_URL}data/monitor_events.json`
const LISTING_TIMES_URL = `${import.meta.env.BASE_URL}data/listing_times.json`
const LAUNCHED_URL = `${import.meta.env.BASE_URL}data/launched.json`
const PROJECTS_URL = `${import.meta.env.BASE_URL}data/projects.json`

/** Safety-net poll. Slows while the workbench socket is delivering radar cards. */
const POLL_MS = 20_000
const POLL_SLOW_MS = 60_000

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

async function fetchRecentCards(): Promise<Candidate[]> {
  try {
    const settings = getApiSettings()
    const base = resolveApiBase(settings.baseUrl || '') || defaultApiBase()
    const body = await fetchRadarRecent(base, settings.token.trim())
    return readRadarCards(body)
  } catch {
    return []
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
  const [httpRecent, setHttpRecent] = useState<Candidate[]>([])
  const inflight = useRef(false)
  const socketOpen = useSyncExternalStore(subscribeBoardSync, isWorkbenchSocketOpen, () => false)
  const radarOverlay = useSyncExternalStore(subscribeRadar, getRadarOverlay, getServerRadarOverlay)
  const blocked = useSyncExternalStore(subscribeBlocklist, getBlockSnapshot, getServerBlockSnapshot)

  const loadDefault = useCallback(async (opts?: { soft?: boolean }) => {
    if (inflight.current) return
    inflight.current = true
    const soft = Boolean(opts?.soft)
    try {
      const [candidatesJson, recentCards, monitor, listingTimesJson, launchedJson, projectsJson] = await Promise.all([
        fetchJson(CANDIDATES_URL),
        fetchRecentCards(),
        soft && events.length ? Promise.resolve({ events, note: eventsNote, generatedAt: eventsAt }) : loadEvents(),
        fetchOptional(LISTING_TIMES_URL),
        fetchOptional(LAUNCHED_URL),
        fetchOptional(PROJECTS_URL),
      ])

      const nextPayload = parsePayload(candidatesJson)
      setPayload(nextPayload)
      setHttpRecent(recentCards)
      if (!soft || !events.length) {
        setEvents(monitor.events)
        setEventsNote(monitor.note)
        setEventsAt(monitor.generatedAt)
      }
      if (listingTimesJson != null) setListingTimes(readListingTimes(listingTimesJson))
      if (launchedJson != null) setLaunched(readLaunched(launchedJson))
      if (projectsJson != null) setProjects(projectsJson)
      setLiveSource(recentCards.length > 0 ? 'api' : 'pages')
      if (!soft) setUploadNote(null)
      setError(null)
    } catch (e) {
      if (!soft) setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
      inflight.current = false
    }
  }, [events, eventsAt, eventsNote])

  useEffect(() => {
    // State is only set after the fetches resolve, not synchronously in the effect.
    // oxlint-disable-next-line react/set-state-in-effect
    void loadDefault()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps -- mount once; polling below

  // Static Pages JSON stays the full list. /v1/radar/recent and the socket are merged on top.
  // While the socket is open this safety net slows from 20s to 60s.
  useEffect(() => {
    const tick = () => {
      if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return
      void loadDefault({ soft: true })
    }
    const id = window.setInterval(tick, socketOpen ? POLL_SLOW_MS : POLL_MS)
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
  }, [loadDefault, socketOpen])

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

  const baseCandidates = useMemo(
    () => mergeRadarCards(mergeRadarCards(payload?.candidates ?? EMPTY_CANDIDATES, httpRecent), radarOverlay),
    [payload, httpRecent, radarOverlay],
  )
  const allCandidates = useMemo(
    () => withProjectPushDates(applyListingTimes(baseCandidates, listingTimes), projects),
    [baseCandidates, listingTimes, projects],
  )
  const launchedView = useMemo(() => {
    const merged = withManualLaunched(launched, blocked.manual)
    return {
      ...merged,
      items: sortLaunchedItems(merged.items, (item) => [item, item.handle ? findByHandle(allCandidates, item.handle) : undefined]),
    }
  }, [launched, blocked, allCandidates])
  const launchedHandles = useMemo(() => {
    const set = launchedHandleSet(launchedView.items)
    for (const handle of blocked.handles) set.add(handle)
    return set
  }, [launchedView, blocked])
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
    launched: launchedView,
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
