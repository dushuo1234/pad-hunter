import { useCallback, useEffect, useMemo, useState } from 'react'
import { Header } from './components/Header'
import { Hero } from './components/Hero'
import { FiltersBar } from './components/Filters'
import { CandidateCard } from './components/CandidateCard'
import { CategoryBoard } from './components/CategoryBoard'
import { DetailDrawer } from './components/DetailDrawer'
import { useTheme } from './hooks/useTheme'
import type { Candidate, CandidatesPayload, Filters, ViewMode } from './types'
import { categoryOf, sortChains } from './utils/categories'

const DEFAULT_FILTERS: Filters = {
  search: '',
  chain: '',
  category: '',
  minFollowers: 0,
  minKol: 0,
  sort: 'date',
}

const DATA_URL = `${import.meta.env.BASE_URL}data/candidates.json`
const EMPTY_CANDIDATES: Candidate[] = []

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
    source: typeof obj.source === 'string' ? obj.source : undefined,
    method: typeof obj.method === 'object' && obj.method ? (obj.method as Record<string, unknown>) : undefined,
    candidates: list as Candidate[],
  }
}

function matches(candidate: Candidate, filters: Filters, ignoreCategory: boolean): boolean {
  if (filters.chain && candidate.chain !== filters.chain) return false
  if ((candidate.followers || 0) < filters.minFollowers) return false
  if ((candidate.kol_followers || 0) < filters.minKol) return false
  if (!ignoreCategory && filters.category && categoryOf(candidate) !== filters.category) return false
  const q = filters.search.trim().toLowerCase()
  if (q) {
    const hay =
      `${candidate.name} ${candidate.handle} ${candidate.why} ${candidate.bio} ${candidate.notes ?? ''} ${candidate.chain} ${categoryOf(candidate)} ${candidate.status ?? ''} ${candidate.listing ?? ''} ${candidate.risk ?? ''}`.toLowerCase()
    if (!hay.includes(q)) return false
  }
  return true
}

function compareCandidates(sort: Filters['sort']) {
  return (a: Candidate, b: Candidate) => {
    if (sort === 'followers') return (b.followers || 0) - (a.followers || 0)
    if (sort === 'kol_followers') return (b.kol_followers || 0) - (a.kol_followers || 0)
    if (sort === 'score') return (b.score || 0) - (a.score || 0) || a.rank - b.rank
    const ta = Date.parse(a.date_iso || '') || 0
    const tb = Date.parse(b.date_iso || '') || 0
    if (tb !== ta) return tb - ta
    return a.rank - b.rank
  }
}

export default function App() {
  const { theme, toggle } = useTheme()
  const [payload, setPayload] = useState<CandidatesPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [view, setView] = useState<ViewMode>('board')
  const [selected, setSelected] = useState<Candidate | null>(null)
  const [uploadNote, setUploadNote] = useState<string | null>(null)

  const loadDefault = useCallback(async () => {
    try {
      const res = await fetch(DATA_URL, { cache: 'no-cache' })
      if (!res.ok) throw new Error(`加载失败 (${res.status})`)
      const json: unknown = await res.json()
      setPayload(parsePayload(json))
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

  const candidates = payload?.candidates ?? EMPTY_CANDIDATES

  const chains = useMemo(
    () => sortChains(new Set(candidates.map((c) => c.chain).filter(Boolean))),
    [candidates],
  )

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const candidate of candidates) {
      if (!matches(candidate, filters, true)) continue
      const key = categoryOf(candidate)
      counts.set(key, (counts.get(key) ?? 0) + 1)
    }
    return counts
  }, [candidates, filters])

  const categories = useMemo(() => {
    const names = new Set(categoryCounts.keys())
    if (filters.category) names.add(filters.category)
    return [...names]
  }, [categoryCounts, filters.category])

  const filtered = useMemo(() => {
    return candidates.filter((c) => matches(c, filters, false)).sort(compareCandidates(filters.sort))
  }, [candidates, filters])

  const categoryCount = useMemo(() => {
    return new Set(candidates.map((c) => categoryOf(c))).size
  }, [candidates])

  const facetedTotal = useMemo(() => {
    let n = 0
    for (const count of categoryCounts.values()) n += count
    return n
  }, [categoryCounts])

  return (
    <div className="min-h-screen bg-[var(--color-cream)] text-[var(--color-ink)] dark:bg-[var(--color-night)] dark:text-[var(--color-night-ink)]">
      <Header theme={theme} onToggleTheme={toggle} onUpload={handleUpload} onRefresh={() => void loadDefault()} />

      <Hero
        projectCount={candidates.length}
        categoryCount={categoryCount}
        chainCount={chains.length}
        generatedAt={payload?.generated_at_utc}
        source={payload?.source}
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

        {error && payload && (
          <p className="mb-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {error}
          </p>
        )}

        {loading && !payload && (
          <div className="rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
            加载项目推送…
          </div>
        )}

        {!loading && error && !payload && (
          <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-6 text-center text-sm text-red-700 dark:border-red-900 dark:bg-red-950/40 dark:text-red-300">
            {error}
            <button type="button" onClick={() => void loadDefault()} className="ml-3 underline">
              重试
            </button>
          </div>
        )}

        {payload && (
          <>
            <FiltersBar
              filters={filters}
              chains={chains}
              categories={categories}
              categoryCounts={categoryCounts}
              resultCount={filtered.length}
              totalCount={facetedTotal}
              view={view}
              onChange={(next) => setFilters((current) => ({ ...current, ...next }))}
              onViewChange={setView}
            />

            <div className="mt-6">
              {filtered.length === 0 && (
                <div className="rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
                  没有匹配的项目，试试放宽链或类型筛选。
                </div>
              )}

              {filtered.length > 0 && view === 'board' && (
                <CategoryBoard candidates={filtered} onOpen={setSelected} />
              )}

              {filtered.length > 0 && view === 'feed' && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {filtered.map((candidate) => (
                    <CandidateCard
                      key={`${candidate.message_id ?? candidate.rank}-${candidate.handle}`}
                      candidate={candidate}
                      onOpen={setSelected}
                    />
                  ))}
                </div>
              )}
            </div>
          </>
        )}
      </main>

      <footer className="border-t border-[var(--color-line)] py-8 text-center dark:border-[var(--color-night-line)]">
        <p className="font-mono text-[11px] text-[var(--color-ink-muted)]">
          台子雷达 · Pad Hunter — Telegram「项目推送」按链与类型分类
        </p>
      </footer>

      <DetailDrawer candidate={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
