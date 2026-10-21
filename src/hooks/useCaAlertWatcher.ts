import { useEffect, useSyncExternalStore } from 'react'
import { useCaFinds } from './useCaFinds'
import {
  observeSightings,
  observeWorkbenchStatus,
  rememberQuiet,
  sightingsFromFinds,
  workbenchLiveCovering,
} from '../utils/caAlert'
import { matchLaunched, type LaunchedItem } from '../utils/launched'
import {
  fetchStatus,
  getApiSettings,
  resolveApiBase,
  subscribeApiSettings,
  type ApiSettings,
} from '../utils/workbenchApi'

const SERVER_SETTINGS: ApiSettings = { token: '', baseUrl: '' }
const POLL_MS = 1000

/** App-level watcher. Mount once so alerts fire on every route. */
export function useCaAlertWatcher(launchedItems: LaunchedItem[], launchedLoading: boolean): void {
  const { finds, launchedArchive, loading, error } = useCaFinds()
  const settings = useSyncExternalStore(subscribeApiSettings, getApiSettings, () => SERVER_SETTINGS)

  useEffect(() => {
    if (loading || error || launchedLoading) return
    const launched = (find: (typeof finds)[number]) => matchLaunched(launchedItems, find) != null
    rememberQuiet([...finds.filter(launched), ...launchedArchive].map((find) => find.address))
    observeSightings('ca', sightingsFromFinds(finds.filter((find) => !launched(find))))
  }, [finds, launchedArchive, launchedItems, launchedLoading, loading, error])

  useEffect(() => {
    const token = settings.token.trim()
    const base = resolveApiBase(settings.baseUrl)
    if (!token) return
    let cancelled = false
    let inflight = false

    const tick = async () => {
      if (cancelled || inflight) return
      if (workbenchLiveCovering() && !document.hidden) return
      inflight = true
      try {
        const status = await fetchStatus(base, token)
        if (!cancelled) observeWorkbenchStatus(status.items)
      } catch {
        // Keep the workbench baseline unset until a payload actually arrives.
      } finally {
        inflight = false
      }
    }

    void tick()
    const timer = window.setInterval(() => void tick(), POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [settings.baseUrl, settings.token])
}
