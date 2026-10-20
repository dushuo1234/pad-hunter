import type { Filters as FiltersState, SortKey } from '../types'
import { sortCategories } from '../utils/categories'

interface FiltersProps {
  filters: FiltersState
  chains: string[]
  categories: string[]
  categoryCounts: Map<string, number>
  resultCount: number
  totalCount: number
  onChange: (next: Partial<FiltersState>) => void
}

const SORTS: [SortKey, string][] = [
  ['date', '最新'],
  ['score', '评分'],
  ['followers', '粉丝'],
  ['kol_followers', 'KOL'],
]

export function FiltersBar({
  filters,
  chains,
  categories,
  categoryCounts,
  resultCount,
  totalCount,
  onChange,
}: FiltersProps) {
  const ordered = sortCategories(categories)
  const dirty =
    Boolean(filters.search || filters.chain || filters.category) ||
    filters.minFollowers > 0 ||
    filters.minKol > 0

  return (
    <div className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 shadow-sm dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] sm:p-5">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
          筛选与排序
        </h2>
        <span className="font-mono text-[11px] text-[var(--color-ink-muted)]">{resultCount} 个结果</span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1.5 lg:col-span-2" htmlFor="filter-search">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            搜索
          </span>
          <input
            id="filter-search"
            name="search"
            type="search"
            placeholder="名称 / handle / 链 / 类型…"
            value={filters.search}
            onChange={(e) => onChange({ search: e.target.value })}
            className="h-10 rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
          />
        </label>

        <label className="flex flex-col gap-1.5" htmlFor="filter-chain">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            链
          </span>
          <select
            id="filter-chain"
            name="chain"
            value={filters.chain}
            onChange={(e) => onChange({ chain: e.target.value })}
            className="h-10 rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
          >
            <option value="">全部链</option>
            {chains.map((chain) => (
              <option key={chain} value={chain}>
                {chain}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5" htmlFor="filter-min-followers">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            最低粉丝
          </span>
          <input
            id="filter-min-followers"
            name="minFollowers"
            type="number"
            min={0}
            step={100}
            value={filters.minFollowers || ''}
            placeholder="0"
            onChange={(e) => onChange({ minFollowers: Number(e.target.value) || 0 })}
            className="h-10 rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 font-mono text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
          />
        </label>

        <label className="flex flex-col gap-1.5" htmlFor="filter-min-kol">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            最低 KOL
          </span>
          <input
            id="filter-min-kol"
            name="minKol"
            type="number"
            min={0}
            step={1}
            value={filters.minKol || ''}
            placeholder="0"
            onChange={(e) => onChange({ minKol: Number(e.target.value) || 0 })}
            className="h-10 rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 font-mono text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
          />
        </label>
      </div>

      <div className="mt-4 border-t border-[var(--color-line)] pt-3 dark:border-[var(--color-night-line)]">
        <div className="mb-2 flex items-center justify-between gap-3">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            类型 / 发射台
          </span>
          {dirty && (
            <button
              type="button"
              onClick={() =>
                onChange({
                  search: '',
                  chain: '',
                  category: '',
                  minFollowers: 0,
                  minKol: 0,
                })
              }
              className="text-xs text-[var(--color-orange-deep)] hover:underline dark:text-[var(--color-orange)]"
            >
              清除筛选
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2" role="group" aria-label="按类型筛选">
          <CategoryChip
            active={!filters.category}
            label="全部"
            count={totalCount}
            onClick={() => onChange({ category: '' })}
          />
          {ordered.map((category) => (
            <CategoryChip
              key={category}
              active={filters.category === category}
              label={category}
              count={categoryCounts.get(category) ?? 0}
              onClick={() => onChange({ category })}
            />
          ))}
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
          排序
        </span>
        {SORTS.map(([key, label]) => (
          <button
            key={key}
            type="button"
            aria-pressed={filters.sort === key}
            onClick={() => onChange({ sort: key })}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              filters.sort === key
                ? 'bg-[var(--color-orange)] text-white'
                : 'border border-[var(--color-line)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]'
            }`}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}

function CategoryChip({
  active,
  label,
  count,
  onClick,
}: {
  active: boolean
  label: string
  count: number
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
        active
          ? 'bg-[var(--color-orange)] text-white'
          : 'border border-[var(--color-line)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]'
      }`}
    >
      {label}
      <span className={`font-mono text-[10px] ${active ? 'text-white/80' : 'text-[var(--color-ink-muted)]'}`}>
        {count}
      </span>
    </button>
  )
}
