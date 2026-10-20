import { useEffect, useState } from 'react'
import type { CaFind } from '../types'
import { CA_FINDS_URL, caFindKey, parseCaFinds } from '../utils/caFinds'

const POLL_MS = 1000

export interface CaFindsState {
  finds: CaFind[]
  generatedAt?: string
  lastChecked: string | null
  loading: boolean
  error: string | null
  freshKeys: Set<string>
}

export function useCaFinds(): CaFindsState {
  const [finds, setFinds] = useState<CaFind[]>([])
  const [generatedAt, setGeneratedAt] = useState<string | undefined>(undefined)
  const [lastChecked, setLastChecked] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [freshKeys, setFreshKeys] = useState<Set<string>>(() => new Set())

  useEffect(() => {
    let cancelled = false
    let timer = 0
    let inflight = false
    let signature = ''
    let baseline: Set<string> | null = null

    const tick = async () => {
      if (inflight) return
      inflight = true
      try {
        const res = await fetch(`${CA_FINDS_URL}?t=${Date.now()}`, { cache: 'no-store' })
        if (!res.ok) throw new Error(`加载失败 (${res.status})`)
        const payload = parseCaFinds(await res.json())
        if (cancelled) return
        const keys = payload.finds.map(caFindKey)
        const nextSignature = `${payload.generated_at ?? ''}\n${keys.join('\n')}`
        if (baseline == null) baseline = new Set(keys)
        if (nextSignature !== signature) {
          signature = nextSignature
          const fresh = new Set<string>()
          for (const key of keys) {
            if (!baseline.has(key)) fresh.add(key)
          }
          setFinds(payload.finds)
          setGeneratedAt(payload.generated_at)
          setFreshKeys(fresh)
        }
        setError(null)
      } catch (reason) {
        if (cancelled) return
        setError(reason instanceof Error ? reason.message : '加载失败')
      } finally {
        inflight = false
        if (!cancelled) {
          setLastChecked(new Date().toISOString())
          setLoading(false)
        }
      }
    }

    // oxlint-disable-next-line react/set-state-in-effect -- state updates run after fetch resolves
    void tick()
    timer = window.setInterval(() => void tick(), POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(timer)
    }
  }, [])

  return { finds, generatedAt, lastChecked, loading, error, freshKeys }
}
