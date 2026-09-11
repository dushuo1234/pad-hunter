import type { Filters as FiltersState, SortKey } from '../types'

interface FiltersProps {
  filters: FiltersState
  chains: string[]
  resultCount: number
  onChange: (next: Partial<FiltersState>) => void
}

export function FiltersBar({ filters, chains, resultCount, onChange }: FiltersProps) {
  return (
    <div className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 shadow-sm dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] sm:p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
          筛选与排序
        </h2>
        <span className="font-mono text-[11px] text-[var(--color-ink-muted)]">
          {resultCount} 个结果
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <label className="flex flex-col gap-1.5 lg:col-span-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            搜索
          </span>
          <input
            type="search"
            placeholder="名称 / handle / why…"
            value={filters.search}
            onChange={(e) => onChange({ search: e.target.value })}
            className="h-10 rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            链
          </span>
          <select
            value={filters.chain}
            onChange={(e) => onChange({ chain: e.target.value })}
            className="h-10 rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
          >
            <option value="">全部链</option>
            {chains.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            最低粉丝
          </span>
          <input
            type="number"
            min={0}
            step={100}
            value={filters.minFollowers || ''}
            placeholder="0"
            onChange={(e) => onChange({ minFollowers: Number(e.target.value) || 0 })}
            className="h-10 rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 font-mono text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            最低 KOL
          </span>
          <input
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

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
          排序
        </span>
        {(
          [
            ['score', '评分'],
            ['followers', '粉丝'],
            ['kol_followers', 'KOL'],
          ] as [SortKey, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
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
