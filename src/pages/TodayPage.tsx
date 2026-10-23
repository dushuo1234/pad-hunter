import { useMemo, useState } from 'react'
import { ConfirmLaunchedButton } from '../components/ConfirmLaunchedButton'
import { PinWorkbenchButton } from '../components/PinWorkbenchButton'
import { PushDate } from '../components/PushDate'
import { ReviewedMark } from '../components/ReviewedMark'
import { SourceBadge } from '../components/SourceBadge'
import { useReviewedMarks } from '../hooks/useReviewed'
import { monitorPath } from '../router'
import type { Candidate, MonitorEvent } from '../types'
import { categoryOf } from '../utils/categories'
import { decodeSnippet, formatLatency, formatShanghai, shortAddr } from '../utils/format'
import { localizeTimelineText } from '../utils/timelineZh'
import {
  launchTimeText,
  listingSourceLabel,
  upcomingLaunches,
  type ListingTimeEntry,
  type UpcomingRow,
} from '../utils/launch'
import { reviewKey, reviewSnapshot } from '../utils/reviewed'

interface TodayPageProps {
  candidates: Candidate[]
  events: MonitorEvent[]
  listingTimes: ListingTimeEntry[]
  loading: boolean
}

export function TodayPage({ candidates, events, listingTimes, loading }: TodayPageProps) {
  const marks = useReviewedMarks()
  const [hideReviewed, setHideReviewed] = useState(false)
  const rows = useMemo(
    () => upcomingLaunches(candidates, events, listingTimes),
    [candidates, events, listingTimes],
  )
  const reviewedCount = rows.filter((row) => {
    const key = reviewKey(row.candidate.handle, row.candidate.name)
    return Boolean(key && marks[key])
  }).length
  const visible = hideReviewed
    ? rows.filter((row) => {
        const key = reviewKey(row.candidate.handle, row.candidate.name)
        return !key || !marks[key]
      })
    : rows

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">尚未开盘</p>
      <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
        即将开盘
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        尚未开盘的项目。开盘时间已经确定、并且落在上海时间今天到第 3 天（含两端）的，按时间从近到远排在前面；开盘时间相同的，再按推送日期从新到旧。没有具体时间，但状态或开盘信号是「即将启动」，或者站点 / JS / is 文件显示项目、合约代码或游戏代码完成度高的，也列在这里，时间写「未知」，不编造时间。已开盘和已开盘归档不会出现。没有开盘时间的按推送日期从新到旧，没有推送日期的放在最后，再按名称排。
      </p>

      {loading && candidates.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          加载即将开盘…
        </div>
      ) : rows.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          这 3 天里没有已确定开盘时间的项目，也没有「即将启动」或完成度高、但时间未知的未开盘项目。
        </div>
      ) : (
        <>
          <div className="mt-4 flex flex-wrap items-center gap-2">
            <button
              type="button"
              aria-pressed={hideReviewed}
              onClick={() => setHideReviewed((current) => !current)}
              className={`inline-flex min-h-9 items-center rounded-lg border px-3 py-1.5 text-xs font-medium ${
                hideReviewed
                  ? 'border-[#166534] bg-[#ecfdf3] text-[#166534] dark:border-[#86efac] dark:bg-[#052e16] dark:text-[#86efac]'
                  : 'border-[var(--color-line)] bg-[var(--color-card)] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]'
              }`}
            >
              隐藏已看
            </button>
            <span className="font-mono text-xs text-[var(--color-ink-muted)]">
              已看 {reviewedCount}/{rows.length}
            </span>
          </div>
          {visible.length === 0 ? (
            <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
              已看的项目已隐藏。
            </div>
          ) : (
            <ul className="mt-6 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
              {visible.map((row) => (
                <TodayRow key={`${row.candidate.source ?? ''}-${row.candidate.handle}`} row={row} />
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  )
}

function TodayRow({ row }: { row: UpcomingRow }) {
  const { candidate: c, launch, snap } = row
  const marks = useReviewedMarks()
  const reviewed = Boolean(marks[reviewKey(c.handle, c.name)])
  const site = snap.lastSite
  const health = site?.status ?? 'unknown'
  const signal = snap.lastSignal?.text
  const source = launch ? listingSourceLabel(launch.source) : ''
  const when = launchTimeText(launch)
  const snapshot = reviewSnapshot({
    listing_at: c.listing_at,
    launch_at: c.launch_at,
    status: c.status,
    listing: c.listing,
    ca: snap.ca || c.ca,
  })
  return (
    <li
      className={`border-b border-[var(--color-line)] px-4 py-3 last:border-b-0 dark:border-[var(--color-night-line)] ${
        reviewed ? 'bg-[var(--color-cream-2)] opacity-75 dark:bg-[var(--color-night)]' : ''
      }`}
    >
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
            <ReviewedMark mode="toggle" handle={c.handle} name={c.name} snapshot={snapshot} />
          </div>
          <p className="mt-0.5 truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
            @{c.handle} · {categoryOf(c)} · {c.chain}
          </p>
          <p className="mt-1">
            <PushDate records={[c]} />
          </p>
        </div>

        <div className="min-w-0">
          <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">开盘时间</div>
          {launch ? (
            <time className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]" dateTime={launch.at}>
              {when}
            </time>
          ) : (
            <div className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{when}</div>
          )}
          {source && <div className="mt-0.5 text-[11px] text-[var(--color-ink-muted)]">来源 {source}</div>}
          {row.tags.length > 0 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {row.tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-md border border-[var(--color-line)] bg-[var(--color-cream-2)] px-1.5 py-0.5 text-[10px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]"
                >
                  {tag}
                </span>
              ))}
            </div>
          )}
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
          <p className="line-clamp-2">{signal ? localizeTimelineText(decodeSnippet(signal)) : '无'}</p>
        </div>

        <a
          href={monitorPath(c.handle)}
          className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline lg:text-right"
        >
          监控详情
        </a>
      </div>
      <div className="mt-3 space-y-2">
        <PinWorkbenchButton candidate={c} variant="button" className="w-full" />
        <ConfirmLaunchedButton candidate={c} className="w-full" />
      </div>
    </li>
  )
}
