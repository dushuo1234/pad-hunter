import { useCaFinds } from '../hooks/useCaFinds'
import { appPath } from '../router'
import { PinWorkbenchButton } from '../components/PinWorkbenchButton'
import { PushDate } from '../components/PushDate'
import { SourceBadge } from '../components/SourceBadge'
import type { Candidate, MonitorEvent } from '../types'
import { findByHandle } from '../utils/candidates'
import { categoryOf } from '../utils/categories'
import { decodeSnippet, formatLatency, formatShanghai, xProfileUrl } from '../utils/format'
import { lockForHandle, safeEvidenceUrl } from '../utils/caFinds'
import { eventsForHandle, siteHealth, snapshotForCandidate } from '../utils/monitor'

interface MonitorPageProps {
  handle: string
  candidates: Candidate[]
  events: MonitorEvent[]
  eventsNote?: string
  eventsAt?: string
}

export function MonitorPage({ handle, candidates, events, eventsNote, eventsAt }: MonitorPageProps) {
  const candidate = findByHandle(candidates, handle)
  const timeline = eventsForHandle(events, handle)
  const snap = candidate ? snapshotForCandidate(candidate, events) : null
  const name = candidate?.name || timeline[0]?.name || handle
  const { locks } = useCaFinds()
  const lock = lockForHandle(locks, handle, name)
  const lockUrl = lock ? safeEvidenceUrl(lock.url) : null

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <a href={appPath()} className="font-mono text-[11px] text-[var(--color-ink-muted)] hover:text-[var(--color-orange)]">
        ← 返回项目
      </a>
      <p className="mt-4 font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">监控详情</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <h1 className="text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
          {name}
        </h1>
        <SourceBadge source={candidate?.source} />
      </div>
      <p className="mt-1 font-mono text-sm text-[var(--color-ink-muted)]">@{handle.replace(/^@/, '')}</p>
      <p className="mt-2">
        <PushDate records={[candidate]} />
      </p>
      {lock && (
        <p className="mt-3 text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
          {lockUrl ? (
            <a
              href={lockUrl}
              target="_blank"
              rel="noreferrer"
              className="mr-2 inline-flex rounded-md border border-[#1d4ed8] bg-[#eff6ff] px-2 py-0.5 text-[11px] font-semibold text-[#1e3a8a] hover:underline dark:border-[#93c5fd] dark:bg-[#172554] dark:text-[#bfdbfe]"
            >
              官推已锁定
            </a>
          ) : (
            <span className="mr-2 inline-flex rounded-md border border-[#1d4ed8] bg-[#eff6ff] px-2 py-0.5 text-[11px] font-semibold text-[#1e3a8a] dark:border-[#93c5fd] dark:bg-[#172554] dark:text-[#bfdbfe]">
              官推已锁定
            </span>
          )}
          锁定只停掉后续非官方 CA 推送。下面的监控钱包和站点动态照常显示。
        </p>
      )}
      <div className="mt-4">
        <PinWorkbenchButton candidate={candidate} name={name} handle={handle} variant="button" />
      </div>

      {!candidate && timeline.length === 0 && (
        <div className="mt-8 rounded-2xl border border-dashed border-[var(--color-line)] px-4 py-10 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          没有找到这个项目。它可能还不在 candidates.json 里。
        </div>
      )}

      {candidate && (
        <>
          <div className="mt-4 flex flex-wrap gap-1.5 text-[11px]">
            <Pill>{categoryOf(candidate)}</Pill>
            <Pill>{candidate.chain}</Pill>
            {candidate.status && <Pill>{candidate.status}</Pill>}
            {candidate.listing && <Pill>{candidate.listing}</Pill>}
          </div>
          {candidate.why && (
            <p className="mt-4 text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
              {candidate.why}
            </p>
          )}
          <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label="状态" value={candidate.status || '—'} />
            <Metric label="CA" value={snap?.ca || '未发现'} mono />
            <Metric
              label="最近站点"
              value={
                snap?.lastSite
                  ? `${snap.lastSite.status === 'up' ? '可用' : snap.lastSite.status === 'down' ? '不可用' : '已探测'}${
                      snap.lastSite.timeS != null ? ` · ${formatLatency(snap.lastSite.timeS)}` : ''
                    }`
                  : candidate.sites?.length
                    ? '尚未探测'
                    : '无站点'
              }
            />
            <Metric label="最近信号" value={snap?.lastSignal ? '有' : '无'} />
          </div>
          {candidate.onchain_notes && (
            <p className="mt-4 rounded-xl border border-[var(--color-line)] bg-[var(--color-card)] px-3 py-3 text-sm text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]">
              {candidate.onchain_notes}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-3 text-sm">
            <a href={xProfileUrl(candidate.handle)} target="_blank" rel="noreferrer" className="text-[var(--color-orange)] hover:underline">
              打开 X
            </a>
            {candidate.sites?.map((site) => (
              <a key={site} href={site} target="_blank" rel="noreferrer" className="truncate text-[var(--color-orange)] hover:underline">
                {site.replace(/^https?:\/\//, '')}
              </a>
            ))}
          </div>
        </>
      )}

      <section className="mt-8">
        <div className="mb-3 flex items-baseline justify-between gap-3">
          <h2 className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">监控时间线</h2>
          <span className="font-mono text-[11px] text-[var(--color-ink-muted)]">
            {timeline.length} 条{eventsAt ? ` · ${formatShanghai(eventsAt)}` : ''}
          </span>
        </div>
        {timeline.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--color-line)] px-4 py-12 text-center dark:border-[var(--color-night-line)]">
            <p className="text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">暂无监控事件</p>
            <p className="mx-auto mt-2 max-w-md text-xs leading-relaxed text-[var(--color-ink-muted)]">
              站点上下线、延迟、开盘信号、合约发现和工厂部署会按时间出现在这里。把记录写入 public/data/monitor_events.json
              后刷新即可。
            </p>
          </div>
        ) : (
          <ol className="relative ml-3 border-l border-[var(--color-line)] dark:border-[var(--color-night-line)]">
            {timeline.map((event) => (
              <li key={event.id} className="relative pb-5 pl-5">
                <span className="absolute top-1.5 -left-[5px] h-2.5 w-2.5 rounded-full bg-[var(--color-orange)]" />
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
                    {eventTitle(event)}
                  </span>
                  {event.sample && (
                    <span className="rounded-md bg-[var(--color-cream-2)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-ink-muted)] dark:bg-[var(--color-night-2)]">
                      示例
                    </span>
                  )}
                  {event.at && (
                    <time className="font-mono text-[11px] text-[var(--color-ink-muted)]" dateTime={event.at}>
                      {formatShanghai(event.at)}
                    </time>
                  )}
                </div>
                <EventBody event={event} />
              </li>
            ))}
          </ol>
        )}
        {eventsNote && <p className="mt-4 text-xs leading-relaxed text-[var(--color-ink-muted)]">{eventsNote}</p>}
      </section>
    </main>
  )
}

function eventTitle(event: MonitorEvent): string {
  if (event.kind === 'site') {
    const health = siteHealth(event.site)
    if (health === 'up') return '站点可用'
    if (health === 'down') return '站点不可用'
    return '站点探测'
  }
  if (event.kind === 'listing_signal') return '开盘信号'
  if (event.kind === 'ca') return '发现合约'
  return '工厂部署'
}

function EventBody({ event }: { event: MonitorEvent }) {
  if (event.kind === 'site' && event.site) {
    const health = siteHealth(event.site)
    return (
      <div className="mt-1 text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        <a href={event.site.url} target="_blank" rel="noreferrer" className="break-all text-[var(--color-orange)] hover:underline">
          {event.site.final_url || event.site.url}
        </a>
        <p className="mt-1 font-mono text-[11px] text-[var(--color-ink-muted)]">
          {health === 'up' ? 'up' : health === 'down' ? 'down' : event.site.status || 'checked'}
          {event.site.http_code ? ` · HTTP ${event.site.http_code}` : ''}
          {event.site.time_s != null ? ` · ${formatLatency(event.site.time_s)}` : ''}
        </p>
        {event.site.error && (
          <p className="mt-2 rounded-lg bg-[var(--color-orange-soft)] px-2 py-2 text-xs text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.12)] dark:text-[var(--color-orange)]">
            {event.site.error}
          </p>
        )}
      </div>
    )
  }
  if (event.kind === 'listing_signal' && event.listing_signal) {
    return (
      <div className="mt-1 text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        <p>{decodeSnippet(event.listing_signal.signal)}</p>
        {(event.listing_signal.keyword || event.listing_signal.source || event.listing_signal.prev) && (
          <p className="mt-1 font-mono text-[11px] text-[var(--color-ink-muted)]">
            {event.listing_signal.keyword ? `keyword ${event.listing_signal.keyword}` : ''}
            {event.listing_signal.source ? ` · ${event.listing_signal.source}` : ''}
            {event.listing_signal.prev ? ` · prev ${event.listing_signal.prev}` : ''}
          </p>
        )}
      </div>
    )
  }
  if (event.kind === 'ca') {
    return (
      <div className="mt-1 text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        <p className="break-all font-mono text-xs">{event.ca}</p>
        <p className="mt-1 font-mono text-[11px] text-[var(--color-ink-muted)]">
          {[event.ca_chain, event.ca_source].filter(Boolean).join(' · ') || '链 / 来源未标注'}
        </p>
        {event.note && <p className="mt-1 text-xs text-[var(--color-ink-muted)]">{event.note}</p>}
      </div>
    )
  }
  const deploy = event.factory_deploy
  if (!deploy) return null
  return (
    <div className="mt-1 space-y-1 text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
      {deploy.notes && <p>{deploy.notes}</p>}
      <p className="break-all font-mono text-[11px] text-[var(--color-ink-muted)]">
        {[
          deploy.chain && `chain ${deploy.chain}`,
          deploy.factory && `factory ${deploy.factory}`,
          deploy.token && `token ${deploy.token}`,
          deploy.tx && `tx ${deploy.tx}`,
          deploy.block != null && `block ${deploy.block}`,
        ]
          .filter(Boolean)
          .join(' · ')}
      </p>
      {event.note && <p className="text-xs text-[var(--color-ink-muted)]">{event.note}</p>}
    </div>
  )
}

function Pill({ children }: { children: string }) {
  return (
    <span className="rounded-md border border-[var(--color-line)] bg-[var(--color-cream-2)] px-2 py-0.5 text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]">
      {children}
    </span>
  )
}

function Metric({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-card)] px-3 py-3 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
      <div
        className={`truncate text-sm font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)] ${mono ? 'font-mono text-xs font-medium' : ''}`}
        title={value}
      >
        {value}
      </div>
      <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">{label}</div>
    </div>
  )
}
