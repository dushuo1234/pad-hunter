import { useMemo } from 'react'
import type { Candidate } from '../types'
import { categoryOf, sortCategories } from '../utils/categories'
import { CandidateCard } from './CandidateCard'

interface CategoryBoardProps {
  candidates: Candidate[]
  onOpen: (c: Candidate) => void
}

export function CategoryBoard({ candidates, onOpen }: CategoryBoardProps) {
  const columns = useMemo(() => {
    const grouped = new Map<string, Candidate[]>()
    for (const candidate of candidates) {
      const key = categoryOf(candidate)
      const list = grouped.get(key)
      if (list) list.push(candidate)
      else grouped.set(key, [candidate])
    }
    return sortCategories(grouped.keys()).map((category) => ({
      category,
      items: grouped.get(category) ?? [],
    }))
  }, [candidates])

  return (
    <div
      className="board-scroll -mx-1 flex gap-3 overflow-x-auto px-1 pb-2"
      role="region"
      aria-label="按类型看板"
    >
      {columns.map((column) => (
        <section
          key={column.category}
          className="board-col flex max-h-[34rem] w-[300px] shrink-0 flex-col rounded-2xl border border-[var(--color-line)] border-t-2 border-t-[var(--color-orange)] bg-[var(--color-cream-2)] dark:border-[var(--color-night-line)] dark:border-t-[var(--color-orange)] dark:bg-[var(--color-night-2)]"
        >
          <header className="flex items-center justify-between gap-2 px-3 py-3">
            <h3 className="truncate text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
              {column.category}
            </h3>
            <span className="rounded-full bg-[var(--color-orange-soft)] px-2 py-0.5 font-mono text-[11px] text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]">
              {column.items.length}
            </span>
          </header>
          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 pb-3">
            {column.items.map((candidate) => (
              <CandidateCard
                key={`${candidate.message_id ?? candidate.rank}-${candidate.handle}`}
                candidate={candidate}
                onOpen={onOpen}
                compact
              />
            ))}
          </div>
        </section>
      ))}
    </div>
  )
}
