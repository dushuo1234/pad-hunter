import { useMemo } from 'react'
import { PinWorkbenchButton } from '../components/PinWorkbenchButton'
import { SourceBadge } from '../components/SourceBadge'
import { monitorPath } from '../router'
import type { Candidate, MonitorEvent } from '../types'
import { categoryOf } from '../utils/categories'
import { decodeSnippet, formatLatency, formatShanghai, shortAddr } from '../utils/format'
import {
  formatLaunchLabel,
  listingSourceLabel,
  upcomingLaunches,
  type ListingTimeEntry,
  type ResolvedLaunch,
} from '../utils/launch'
import type { MonitorSnapshot } from '../utils/monitor'

interface TodayPageProps {
  candidates: Candidate[]
  events: MonitorEvent[]
  listingTimes: ListingTimeEntry[]
  loading: boolean
}

export function TodayPage({ candidates, events, listingTimes, loading }: TodayPageProps) {
  const rows = useMemo(
    () => upcomingLaunches(candidates, events, listingTimes),
    [candidates, events, listingTimes],
  )

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">未来 3 天 · 尚未开盘</p>
      <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
        即将开盘
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        只显示尚未开盘、并且能解析出开盘时间的项目。时间按上海时间，从今天到第 3 天（含两端）。只写「即将开盘」、没有具体时间的不会出现；已开盘、已上线、正在交易的也不会出现。按开盘时间从近到远排列。
      </p>

      {loading && candidates.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          加载即将开盘…
        </div>
      ) : rows.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          未来 3 天没有尚未开盘、且带开盘时间的项目。
        </div>
      ) : (
        <ul className="mt-6 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
          {rows.map((row) => (
            <TodayRow key={`${row.candidate.source ?? ''}-${row.candidate.handle}`} row={row} />
          ))}
        </ul>
      )}
    </main>
  )
}

function TodayRow({ row }: { row: { candidate: Candidate; launch: ResolvedLaunch; snap: MonitorSnapshot } }) {
  const { candidate: c, launch, snap } = row
  const site = snap.lastSite
  const health = site?.status ?? 'unknown'
  const signal = snap.lastSignal?.text
  const source = listingSourceLabel(launch.source)
  return (
    <li className="border-b border-[var(--color-line)] px-4 py-3 last:border-b-0 dark:border-[var(--color-night-line)]">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)_minmax(0,0.9fr)_minmax(0,1.2fr)_auto] lg:items-center">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <a
              href={monitorPath(c.handle)}
              className="truncate text-sm font-semibold text-[var(--color-ink)] hover:text-[var(--color-orange-deep)] dark:text-[var(--color-night-ink)] dark:hover:text-[var(--color-orange)]"
            >
              {c.name}
            </a>
            <SourceBadge source={c.source} />
            {c.listing && (
              <span className="rounded-md border border-[var(--color-line)] bg-[var(--color-cream-2)] px-2 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]">
                {c.listing}
              </span>
            )}
          </div>
          <p className="mt-0.5 truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
            @{c.handle} · {categoryOf(c)} · {c.chain}
          </p>
        </div>

        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">开盘时间</div>
          <time className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]" dateTime={launch.at}>
            {formatLaunchLabel(launch)}
          </time>
          {source && <div className="mt-0.5 text-[11px] text-[var(--color-ink-muted)]">来源 {source}</div>}
        </div>

        <div className="min-w-0 text-xs text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
          <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">CA</div>
          <div className="truncate font-mono" title={snap.ca || undefined}>
            {snap.ca ? shortAddr(snap.ca) : '未发现'}
          </div>
          <div className="mt-1 font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">最近站点</div>
          {site ? (
            <div className={health === 'down' ? 'text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]' : ''}>
              {health === 'up' ? '可用' : health === 'down' ? '不可用' : '已探测'}
              {site.timeS != null ? ` · ${formatLatency(site.timeS)}` : ''}
              {site.at ? ` · ${formatShanghai(site.at)}` : ''}
            </div>
          ) : (
            <div>{c.sites && c.sites.length > 0 ? '有站点，尚未探测' : '无站点'}</div>
          )}
        </div>

        <div className="min-w-0 text-xs leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
          <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">最近信号</div>
          <p className="line-clamp-2">{signal ? decodeSnippet(signal) : '无'}</p>
        </div>

        <a
          href={monitorPath(c.handle)}
          className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline lg:text-right"
        >
          监控详情
        </a>
      </div>
      <div className="mt-3">
        <PinWorkbenchButton candidate={c} variant="button" className="w-full" />
      </div>
    </li>
  )
}
