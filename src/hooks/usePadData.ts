import { useCallback, useEffect, useMemo, useState } from 'react'
import type { Candidate, CandidatesPayload, MonitorEvent } from '../types'
import { withSourceFallback } from '../utils/candidates'
import { withProjectPushDates } from '../utils/pushDate'
import { applyListingTimes, readListingTimes, type ListingTimeEntry } from '../utils/launch'
import { launchedHandleSet, readLaunched, withoutLaunched, type LaunchedDocument } from '../utils/launched'
import { collectMonitorEvents, listedMonitorFiles, readMonitorDocument } from '../utils/monitor'

const CANDIDATES_URL = `${import.meta.env.BASE_URL}data/candidates.json`
const EVENTS_URL = `${import.meta.env.BASE_URL}data/monitor_events.json`
const LISTING_TIMES_URL = `${import.meta.env.BASE_URL}data/listing_times.json`
const LAUNCHED_URL = `${import.meta.env.BASE_URL}data/launched.json`
const PROJECTS_URL = `${import.meta.env.BASE_URL}data/projects.json`

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

async function fetchJson(url: string): Promise<unknown> {
  const res = await fetch(url, { cache: 'no-cache' })
  if (!res.ok) throw new Error(`加载失败 (${res.status})`)
  return res.json()
}

async function fetchOptional(url: string): Promise<unknown | null> {
  try {
    const res = await fetch(url, { cache: 'no-cache' })
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

  const loadDefault = useCallback(async () => {
    try {
      const [candidatesJson, monitor, listingTimesJson, launchedJson, projectsJson] = await Promise.all([
        fetchJson(CANDIDATES_URL),
        loadEvents(),
        fetchOptional(LISTING_TIMES_URL),
        fetchOptional(LAUNCHED_URL),
        fetchOptional(PROJECTS_URL),
      ])
      setPayload(parsePayload(candidatesJson))
      setEvents(monitor.events)
      setEventsNote(monitor.note)
      setEventsAt(monitor.generatedAt)
      setListingTimes(readListingTimes(listingTimesJson))
      setLaunched(readLaunched(launchedJson))
      setProjects(projectsJson)
      setUploadNote(null)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // oxlint-disable-next-line react/set-state-in-effect -- state updates run after fetch resolves
    void loadDefault()
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
    loadDefault,
    handleUpload,
    candidates,
    allCandidates,
  }
}
