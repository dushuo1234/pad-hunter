import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import type { Candidate } from '../types'
import {
  checkWorkbench,
  clearApiToken,
  defaultApiBase,
  emptyLaunched,
  errorText,
  fetchHealth,
  fetchLaunched,
  fetchStatus,
  getApiSettings,
  isAuthError,
  resolveApiBase,
  saveApiSettings,
  statusIndex,
  subscribeApiSettings,
  syncItemsFromPins,
  syncWorkbench,
  type ApiSettings,
  type HealthInfo,
  type LaunchedIndex,
  type WorkbenchStatusItem,
} from '../utils/workbenchApi'
import { handleKey } from '../utils/workbench'
import { useWorkbenchItems } from './useWorkbench'

const SERVER_SETTINGS: ApiSettings = { token: '', baseUrl: '' }
const EMPTY_ROWS: WorkbenchStatusItem[] = []

interface CheckingMeta {
  since: number
  previousCheckAt: string
}

export function useWorkbenchLive(candidates: Candidate[]) {
  const items = useWorkbenchItems()
  const settings = useSyncExternalStore(subscribeApiSettings, getApiSettings, () => SERVER_SETTINGS)
  const token = settings.token.trim()
  const base = resolveApiBase(settings.baseUrl)
  const syncItems = useMemo(() => syncItemsFromPins(items, candidates), [items, candidates])

  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [healthState, setHealthState] = useState<'unknown' | 'online' | 'offline'>('unknown')
  const [snapshot, setSnapshot] = useState<{
    token: string
    base: string
    rows: WorkbenchStatusItem[]
    hasStatus: boolean
    error: string | null
  }>({ token: '', base: '', rows: [], hasStatus: false, error: null })
  const fresh = snapshot.token === token && snapshot.base === base
  const rows = fresh ? snapshot.rows : EMPTY_ROWS
  const hasStatus = fresh && snapshot.hasStatus
  const statusError = fresh ? snapshot.error : null
  const [syncState, setSyncState] = useState<'idle' | 'syncing' | 'ok' | 'error'>('idle')
  const [syncMessage, setSyncMessage] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [authFor, setAuthFor] = useState('')
  const [launched, setLaunched] = useState<LaunchedIndex>(() => emptyLaunched())
  const [now, setNow] = useState(() => Date.now())
  const [checking, setChecking] = useState<ReadonlySet<string>>(() => new Set())
  const [detailTick, setDetailTick] = useState(0)

  const checkingRef = useRef<Map<string, CheckingMeta>>(new Map())
  const sessionRef = useRef({ token, base })

  useEffect(() => {
    sessionRef.current = { token, base }
  }, [token, base])

  const noteAuth = useCallback((error: unknown) => {
    if (isAuthError(error)) setAuthFor(token)
  }, [token])

  const pullStatus = useCallback(async () => {
    const requestedToken = token
    const requestedBase = base
    if (!requestedToken) return
    const current = () => sessionRef.current.token === requestedToken && sessionRef.current.base === requestedBase
    try {
      const parsed = await fetchStatus(requestedBase, requestedToken)
      if (!current()) return
      setAuthFor((authToken) => (authToken === requestedToken ? '' : authToken))
      setSnapshot({
        token: requestedToken,
        base: requestedBase,
        rows: parsed.items,
        hasStatus: true,
        error: null,
      })
      const index = statusIndex(parsed.items)
      let changed = false
      let finished = false
      for (const [key, meta] of checkingRef.current) {
        const item = index.get(key)
        const done = Boolean(item && !item.checking && item.lastCheckAt && item.lastCheckAt !== meta.previousCheckAt)
        const timedOut = Date.now() - meta.since > 60_000
        if (done || timedOut) {
          checkingRef.current.delete(key)
          changed = true
          if (done) finished = true
        }
      }
      if (changed) setChecking(new Set(checkingRef.current.keys()))
      if (finished) setDetailTick((value) => value + 1)
    } catch (error) {
      if (!current()) return
      noteAuth(error)
      const message = errorText(error)
      setSnapshot((currentSnapshot) => ({
        token: requestedToken,
        base: requestedBase,
        rows: currentSnapshot.token === requestedToken && currentSnapshot.base === requestedBase ? currentSnapshot.rows : [],
        hasStatus: currentSnapshot.token === requestedToken && currentSnapshot.base === requestedBase ? currentSnapshot.hasStatus : false,
        error: message,
      }))
    }
  }, [base, noteAuth, token])

  useEffect(() => {
    let alive = true
    void fetchLaunched().then((index) => {
      if (alive) setLaunched(index)
    })
    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    if (!token) return
    let cancelled = false
    const timer = window.setTimeout(() => {
      void (async () => {
        setSyncState('syncing')
        try {
          const count = await syncWorkbench(base, token, syncItems)
          if (cancelled) return
          setAuthFor((current) => (current === token ? '' : current))
          setSyncState('ok')
          setSyncMessage(`已同步 ${count} 个目标`)
        } catch (error) {
          if (cancelled) return
          noteAuth(error)
          setSyncState('error')
          setSyncMessage(errorText(error))
        }
      })()
    }, 500)
    return () => {
      cancelled = true
      window.clearTimeout(timer)
    }
  }, [syncItems, token, base, noteAuth])

  useEffect(() => {
    let alive = true
    let timer = 0
    let generation = 0
    let healthTicks = 0

    const pullHealth = async () => {
      try {
        const info = await fetchHealth(base, token)
        if (!alive) return
        setHealth(info)
        setHealthState(info.ok ? 'online' : 'offline')
      } catch {
        if (!alive) return
        setHealthState('offline')
      }
    }

    const loop = async () => {
      const gen = ++generation
      if (!alive || document.hidden) return
      const tasks: Promise<void>[] = []
      if (healthTicks % 5 === 0) tasks.push(pullHealth())
      healthTicks += 1
      if (token) tasks.push(pullStatus())
      await Promise.all(tasks)
      if (!alive || document.hidden || gen !== generation) return
      setNow(Date.now())
      timer = window.setTimeout(() => void loop(), 1000)
    }

    const onVisibility = () => {
      window.clearTimeout(timer)
      if (!document.hidden) void loop()
    }

    void loop()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      alive = false
      generation += 1
      window.clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [token, base, pullStatus])

  const checkNow = useCallback(
    async (handle: string) => {
      const key = handleKey(handle)
      if (!key) {
        setActionError('没有 X 账号，无法检查')
        return
      }
      if (!token) {
        setActionError('请填写监控接口令牌')
        return
      }
      const previous = statusIndex(rows).get(key)?.lastCheckAt ?? ''
      checkingRef.current.set(key, { since: Date.now(), previousCheckAt: previous })
      setChecking(new Set(checkingRef.current.keys()))
      setActionError(null)
      try {
        const queued = await checkWorkbench(base, token, handle.trim())
        if (!queued) {
          const failure = { status: 0, message: '检查未排队' }
          throw failure
        }
        await pullStatus()
      } catch (error) {
        checkingRef.current.delete(handleKey(handle))
        setChecking(new Set(checkingRef.current.keys()))
        noteAuth(error)
        setActionError(errorText(error))
      }
    },
    [base, noteAuth, pullStatus, rows, token],
  )

  const isChecking = useCallback((handle: string) => checking.has(handleKey(handle)), [checking])

  return {
    items,
    settings,
    token,
    base,
    defaultBase: defaultApiBase(),
    saveSettings: saveApiSettings,
    clearToken: clearApiToken,
    health,
    healthState,
    statusByHandle: useMemo(() => statusIndex(token ? rows : []), [rows, token]),
    hasStatus: Boolean(token) && hasStatus,
    syncState: token ? syncState : 'idle',
    syncMessage: token ? syncMessage : null,
    statusError: token ? statusError : null,
    actionError,
    authError: Boolean(token) && authFor === token,
    launched,
    now,
    detailTick,
    checkNow,
    isChecking,
  }
}
