import { useEffect, useMemo, useState } from 'react'
import { CandidateCard } from '../components/CandidateCard'
import { DetailDrawer } from '../components/DetailDrawer'
import { FiltersBar } from '../components/Filters'
import { Hero } from '../components/Hero'
import type { Candidate, CandidatesPayload, Filters } from '../types'
import { compareCandidates, matches, sortSources } from '../utils/candidates'
import { categoryOf, sortChains } from '../utils/categories'

const DEFAULT_FILTERS: Filters = {
  search: '',
  chain: '',
  category: '',
  source: '',
  minFollowers: 0,
  minKol: 0,
  sort: 'date',
}

interface HomePageProps {
  payload: CandidatesPayload | null
  candidates: Candidate[]
  loading: boolean
  error: string | null
  uploadNote: string | null
  onRetry: () => void
}

export function HomePage({ payload, candidates, loading, error, uploadNote, onRetry }: HomePageProps) {
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS)
  const [selected, setSelected] = useState<Candidate | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelected(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Close the drawer when a refresh drops the selected project.
  const openCandidate = useMemo(() => {
    if (!selected) return null
    const key = selected.handle.replace(/^@/, '').trim().toLowerCase()
    if (!key || !candidates.some((candidate) => candidate.handle.replace(/^@/, '').trim().toLowerCase() === key)) {
      return null
    }
    return selected
  }, [candidates, selected])

  const chains = useMemo(
    () => sortChains(new Set(candidates.map((c) => c.chain).filter(Boolean))),
    [candidates],
  )

  const sources = useMemo(
    () => sortSources(candidates.map((c) => c.source).filter((source): source is string => Boolean(source))),
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

  const sourceCounts = useMemo(() => {
    const counts = new Map<string, number>()
    const sourceFilters = { ...filters, source: '' }
    for (const candidate of candidates) {
      if (!matches(candidate, sourceFilters, false) || !candidate.source) continue
      counts.set(candidate.source, (counts.get(candidate.source) ?? 0) + 1)
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

  const categoryCount = useMemo(() => new Set(candidates.map((c) => categoryOf(c))).size, [candidates])

  const facetedTotal = useMemo(() => {
    let n = 0
    for (const count of categoryCounts.values()) n += count
    return n
  }, [categoryCounts])

  return (
    <>
      <Hero
        projectCount={candidates.length}
        categoryCount={categoryCount}
        chainCount={chains.length}
        generatedAt={payload?.generated_at_utc}
        sources={payload?.sources?.length ? payload.sources : sources}
      />

      <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
        {payload?.goal && (
          <p className="mb-5 rounded-xl border border-[var(--color-line)] bg-[var(--color-orange-soft)] px-4 py-3 text-sm text-[var(--color-orange-deep)] dark:border-[rgba(232,135,58,0.25)] dark:bg-[rgba(232,135,58,0.1)] dark:text-[var(--color-orange)]">
            {payload.goal}
          </p>
        )}

        {uploadNote && <p className="mb-4 font-mono text-xs text-[var(--color-ink-muted)]">{uploadNote}</p>}

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
            <button type="button" onClick={onRetry} className="ml-3 underline">
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
              sources={sources}
              sourceCounts={sourceCounts}
              resultCount={filtered.length}
              totalCount={facetedTotal}
              onChange={(next) => setFilters((current) => ({ ...current, ...next }))}
            />

            <div className="mt-6">
              {filtered.length === 0 && (
                <div className="rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
                  没有匹配的项目，试试放宽链或类型筛选。
                </div>
              )}

              {filtered.length > 0 && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {filtered.map((candidate) => (
                    <CandidateCard
                      key={`${candidate.source ?? ''}-${candidate.message_id ?? candidate.rank}-${candidate.handle}`}
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

      <DetailDrawer candidate={openCandidate} onClose={() => setSelected(null)} />
    </>
  )
}
