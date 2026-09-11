import { useCallback, useEffect, useMemo, useState } from 'react'
import { Header } from './components/Header'
import { Hero } from './components/Hero'
import { FiltersBar } from './components/Filters'
import { CandidateCard } from './components/CandidateCard'
import { DetailDrawer } from './components/DetailDrawer'
import { useTheme } from './hooks/useTheme'
import type { Candidate, CandidatesPayload, Filters } from './types'

const DEFAULT_FILTERS: Filters = {
  search: '',
  chain: '',
  minFollowers: 0,
  minKol: 0,
  sort: 'score',
}

function parsePayload(data: unknown): CandidatesPayload {
  if (!data || typeof data !== 'object') throw new Error('无效的 JSON')
  const obj = data as Record<string, unknown>
  const list = Array.isArray(obj.candidates)
    ? obj.candidates
    : Array.isArray(data)
      ? data
      : null
  if (!list) throw new Error('JSON 需包含 candidates 数组')
  return {
    generated_at_utc: typeof obj.generated_at_utc === 'string' ? obj.generated_at_utc : undefined,
    goal: typeof obj.goal === 'string' ? obj.goal : undefined,
    method: typeof obj.method === 'object' && obj.method ? (obj.method as Record<string, unknown>) : undefined,
    candidates: list as Candidate[],
  }
}

export default function App() {
  const { theme, toggle } = useTheme()
  const [payload, setPayload] = useState<CandidatesPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [selected, setSelected] = useState<Candidate | null>(null)
  const [uploadNote, setUploadNote] = useState<string | null>(null)

  const loadDefault = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch('/data/candidates.json')
      if (!res.ok) throw new Error(`加载失败 (${res.status})`)
      const json: unknown = await res.json()
      setPayload(parsePayload(json))
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadDefault()
  }, [loadDefault])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const handleUpload = async (file: File) => {
    try {
      const text = await file.text()
      const json: unknown = JSON.parse(text)
      const parsed = parsePayload(json)
      setPayload(parsed)
      setUploadNote(`已加载 ${file.name}（仅本次会话）`)
      setError(null)
      setFilters(DEFAULT_FILTERS)
      setSelected(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : '上传解析失败')
    }
  }

  const candidates = payload?.candidates ?? []

  const chains = useMemo(() => {
    const set = new Set(candidates.map((c) => c.chain).filter(Boolean))
    return Array.from(set).sort((a, b) => a.localeCompare(b))
  }, [candidates])

  const filtered = useMemo(() => {
    const q = filters.search.trim().toLowerCase()
    const list = candidates.filter((c) => {
      if (filters.chain && c.chain !== filters.chain) return false
      if (c.followers < filters.minFollowers) return false
      if (c.kol_followers < filters.minKol) return false
      if (q) {
        const hay = `${c.name} ${c.handle} ${c.why} ${c.bio} ${c.notes ?? ''} ${c.chain}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      return true
    })

    const sorted = [...list].sort((a, b) => {
      if (filters.sort === 'followers') return b.followers - a.followers
      if (filters.sort === 'kol_followers') return b.kol_followers - a.kol_followers
      return b.score - a.score
    })
    return sorted
  }, [candidates, filters])

  const avgScore =
    candidates.length === 0
      ? 0
      : candidates.reduce((s, c) => s + (c.score || 0), 0) / candidates.length

  return (
    <div className="min-h-screen bg-[var(--color-cream)] text-[var(--color-ink)] dark:bg-[var(--color-night)] dark:text-[var(--color-night-ink)]">
      <Header theme={theme} onToggleTheme={toggle} onUpload={handleUpload} />

      <Hero
        projectCount={candidates.length}
        avgScore={avgScore}
        chainCount={chains.length}
        generatedAt={payload?.generated_at_utc}
      />

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {payload?.goal && (
          <p className="mb-5 rounded-xl border border-[var(--color-line)] bg-[var(--color-orange-soft)] px-4 py-3 text-sm text-[var(--color-orange-deep)] dark:border-[rgba(232,135,58,0.25)] dark:bg-[rgba(232,135,58,0.1)] dark:text-[var(--color-orange)]">
            {payload.goal}
          </p>
        )}

        {uploadNote && (
          <p className="mb-4 font-mono text-xs text-[var(--color-ink-muted)]">{uploadNote}</p>
        )}

        <FiltersBar
          filters={filters}
          chains={chains}
          resultCount={filtered.length}
          onChange={(next) => setFilters((f) => ({ ...f, ...next }))}
        />

        <div className="mt-6">
          {loading && (
            <div className="rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
              加载候选数据…
            </div>
          )}

          {!loading && error && (
            <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-6 text-center text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
              {error}
              <button
                type="button"
                onClick={() => void loadDefault()}
                className="ml-3 underline"
              >
                重试
              </button>
            </div>
          )}

          {!loading && !error && filtered.length === 0 && (
            <div className="rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
              没有匹配的项目，试试放宽筛选条件。
            </div>
          )}

          {!loading && !error && filtered.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2">
              {filtered.map((c) => (
                <CandidateCard
                  key={`${c.rank}-${c.handle}`}
                  candidate={c}
                  onOpen={setSelected}
                />
              ))}
            </div>
          )}
        </div>
      </main>

      <footer className="border-t border-[var(--color-line)] py-8 text-center dark:border-[var(--color-night-line)]">
        <p className="font-mono text-[11px] text-[var(--color-ink-muted)]">
          台子雷达 · Pad Hunter — Launchpad 产品猎人，非 meme 代币扫描
        </p>
      </footer>

      <DetailDrawer candidate={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
