import { useMemo, useState } from 'react'
import { PinWorkbenchButton } from '../components/PinWorkbenchButton'
import { SourceBadge } from '../components/SourceBadge'
import { monitorPath } from '../router'
import type { Candidate, MonitorEvent } from '../types'
import { categoryOf } from '../utils/categories'
import { decodeSnippet, formatLatency, formatShanghai, shortAddr } from '../utils/format'
import { snapshotForCandidate, type MonitorSnapshot } from '../utils/monitor'
import { openingReasons, openingWeight, type OpeningReason } from '../utils/opening'

type BoardFilter = 'all' | OpeningReason['id']

const FILTERS: { id: BoardFilter; label: string }[] = [
  { id: 'all', label: '全部盯盘' },
  { id: 'today', label: '今日开盘' },
  { id: 'mint', label: 'mint进行中' },
  { id: 'soon', label: '即将启动' },
  { id: 'signal', label: '开盘信号' },
]

interface TodayPageProps {
  candidates: Candidate[]
  events: MonitorEvent[]
  loading: boolean
}

interface Row {
  candidate: Candidate
  reasons: OpeningReason[]
  snap: MonitorSnapshot
}

export function TodayPage({ candidates, events, loading }: TodayPageProps) {
  const [filter, setFilter] = useState<BoardFilter>('all')
  const rows = useMemo(() => {
    const list: Row[] = []
    for (const candidate of candidates) {
      const snap = snapshotForCandidate(candidate, events)
      const reasons = openingReasons(candidate, snap)
      if (reasons.length === 0) continue
      list.push({ candidate, reasons, snap })
    }
    list.sort((a, b) => {
      const weight = openingWeight(a.reasons) - openingWeight(b.reasons)
      if (weight !== 0) return weight
      const downA = a.snap.lastSite?.status === 'down' ? 0 : 1
      const downB = b.snap.lastSite?.status === 'down' ? 0 : 1
      if (downA !== downB) return downA - downB
      return (Date.parse(b.candidate.date_iso || '') || 0) - (Date.parse(a.candidate.date_iso || '') || 0)
    })
    return list
  }, [candidates, events])

  const counts = useMemo(() => {
    const map = new Map<BoardFilter, number>()
    map.set('all', rows.length)
    for (const id of ['today', 'mint', 'soon', 'signal'] as const) {
      map.set(id, rows.filter((row) => row.reasons.some((reason) => reason.id === id)).length)
    }
    return map
  }, [rows])

  const visible = filter === 'all' ? rows : rows.filter((row) => row.reasons.some((reason) => reason.id === filter))

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">尚未开盘</p>
      <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
        今日即将开盘
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        只列尚未开盘的项目：预计今天开盘，或状态为 mint进行中 / 即将启动 / 即将开盘，或扫描里已有开盘信号。已开盘、已上线、正在交易的不会出现。状态、合约、最近一次站点探测和最近一条信号放在同一行。
      </p>

      {loading && candidates.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          加载盯盘列表…
        </div>
      ) : (
        <>
          <div className="mt-6 flex flex-wrap gap-2" role="group" aria-label="盯盘范围">
            {FILTERS.map((item) => {
              const count = counts.get(item.id) ?? 0
              if (item.id !== 'all' && count === 0) return null
              const active = filter === item.id
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setFilter(item.id)}
                  className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
                    active
                      ? 'bg-[var(--color-orange)] text-white'
                      : 'border border-[var(--color-line)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]'
                  }`}
                >
                  {item.label}
                  <span className={`font-mono text-[10px] ${active ? 'text-white/80' : 'text-[var(--color-ink-muted)]'}`}>
                    {count}
                  </span>
                </button>
              )
            })}
          </div>

          {visible.length === 0 ? (
            <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
              今天没有尚未开盘的盯盘项目。
            </div>
          ) : (
            <ul className="mt-4 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
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

function TodayRow({ row }: { row: Row }) {
  const { candidate: c, reasons, snap } = row
  const site = snap.lastSite
  const health = site?.status ?? 'unknown'
  const signal = snap.lastSignal?.text
  return (
    <li className="border-b border-[var(--color-line)] px-4 py-3 last:border-b-0 dark:border-[var(--color-night-line)]">
      <div className="grid gap-3 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.7fr)_minmax(0,0.9fr)_minmax(0,1.3fr)_auto] lg:items-center">
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

        <div className="flex flex-wrap gap-1.5">
          {reasons.map((reason) => (
            <span
              key={reason.id}
              className="rounded-md bg-[var(--color-orange-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]"
            >
              {reason.label}
            </span>
          ))}
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

