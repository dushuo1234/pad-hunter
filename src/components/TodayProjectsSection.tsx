import { useEffect, useState } from 'react'
import { monitorPath } from '../router'
import { formatShanghai, xProfileUrl } from '../utils/format'
import {
  playbookGroups,
  todayProjectsToShow,
  todayTimeView,
  type TodayProject,
  type TodayProjectsDocument,
  type TodayTimeView,
} from '../utils/todayProjects'

const LINK =
  'font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline'

const TIME_LABEL: Record<TodayTimeView['kind'], string> = {
  countdown: '倒计时',
  display: '开盘时间',
  hours: '距开盘',
}

export function TodayProjectsSection({
  projects,
  className = '',
}: {
  projects: TodayProjectsDocument | null
  className?: string
}) {
  const items = todayProjectsToShow(projects)
  if (items.length === 0) return null
  const generated = projects?.generated_at
  const updated = generated ? formatShanghai(generated) || generated : ''

  return (
    <section aria-label="今日项目清单" className={`mb-6 ${className}`.trim()}>
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div>
          <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">48 小时内开盘</p>
          <h2 className="mt-1 text-xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
            今日项目清单
          </h2>
        </div>
        <p className="font-mono text-[11px] text-[var(--color-ink-muted)]">
          {items.length} 个
          {updated ? ` · 更新 ${updated}` : ''}
        </p>
      </div>
      <ul className="mt-3 space-y-3">
        {items.map((item, index) => (
          <TodayProjectCard key={`${item.handle}-${item.listing_at ?? ''}-${index}`} item={item} />
        ))}
      </ul>
    </section>
  )
}

function TodayProjectCard({ item }: { item: TodayProject }) {
  const groups = playbookGroups(item.playbook)
  const sources = item.playbook?.来源 ?? []
  const summary = item.playbook?.summary
  const playbookAt = item.playbook?.updated_at
  const playbookUpdated = playbookAt ? formatShanghai(playbookAt) || playbookAt : ''
  const profile = item.handle ? xProfileUrl(item.handle) : ''
  return (
    <li className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] px-4 py-3.5 shadow-[inset_3px_0_0_var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {item.handle ? (
              <a
                href={monitorPath(item.handle)}
                className="truncate text-[15px] font-semibold text-[var(--color-ink)] hover:text-[var(--color-orange-deep)] dark:text-[var(--color-night-ink)] dark:hover:text-[var(--color-orange)]"
              >
                {item.name}
              </a>
            ) : (
              <h3 className="truncate text-[15px] font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{item.name}</h3>
            )}
            {item.status && (
              <span className="rounded-md border border-transparent bg-[var(--color-orange-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]">
                {item.status}
              </span>
            )}
          </div>
          {(item.handle || item.chain) && (
            <p className="mt-0.5 truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
              {item.handle &&
                (profile ? (
                  <a href={profile} target="_blank" rel="noreferrer" className="hover:text-[var(--color-orange)]">
                    @{item.handle}
                  </a>
                ) : (
                  <span>@{item.handle}</span>
                ))}
              {item.handle && item.chain ? ' · ' : ''}
              {item.chain}
            </p>
          )}
          {(item.site || item.tweet_url) && (
            <p className="mt-2 flex flex-wrap gap-3">
              {item.site && (
                <a href={item.site} target="_blank" rel="noreferrer" className={LINK}>
                  官网
                </a>
              )}
              {item.tweet_url && (
                <a href={item.tweet_url} target="_blank" rel="noreferrer" className={LINK}>
                  X
                </a>
              )}
            </p>
          )}
        </div>
        <ProjectClock item={item} />
      </div>

      {(summary || groups.length > 0 || sources.length > 0) && (
        <div className="mt-3 border-t border-[var(--color-line)] pt-3 dark:border-[var(--color-night-line)]">
          {summary && (
            <p className="text-sm leading-relaxed text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{summary}</p>
          )}
          {playbookUpdated && (
            <p className="mt-1 font-mono text-[10px] text-[var(--color-ink-muted)]">玩法更新 {playbookUpdated}</p>
          )}
          {groups.length > 0 && (
            <dl className="mt-3 grid gap-3 sm:grid-cols-2">
              {groups.map((group) => (
                <div key={group.label}>
                  <dt
                    className={`font-mono text-[10px] tracking-wider ${
                      group.label === '风险注意'
                        ? 'text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]'
                        : 'text-[var(--color-ink-muted)]'
                    }`}
                  >
                    {group.label}
                  </dt>
                  <dd className="mt-1">
                    {group.label === '步骤' ? (
                      <ol className="list-decimal space-y-0.5 pl-4 text-xs leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
                        {group.lines.map((line, lineIndex) => (
                          <li key={`${line}-${lineIndex}`}>{line}</li>
                        ))}
                      </ol>
                    ) : (
                      <ul className="list-disc space-y-0.5 pl-4 text-xs leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
                        {group.lines.map((line, lineIndex) => (
                          <li key={`${line}-${lineIndex}`}>{line}</li>
                        ))}
                      </ul>
                    )}
                  </dd>
                </div>
              ))}
            </dl>
          )}
          {sources.length > 0 && (
            <p className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
              <span className="font-mono text-[10px] tracking-wider text-[var(--color-ink-muted)]">来源</span>
              {sources.map((source) => (
                <a key={source.url} href={source.url} target="_blank" rel="noreferrer" className={LINK}>
                  {source.label}
                </a>
              ))}
            </p>
          )}
        </div>
      )}
    </li>
  )
}

function ProjectClock({ item }: { item: TodayProject }) {
  const live = Boolean(item.listing_at) && !Number.isNaN(Date.parse(item.listing_at ?? ''))
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    if (!live) return
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [live])
  const view = todayTimeView(item, now)
  if (!view) return null
  return (
    <div className="shrink-0 text-right">
      <div className="font-mono text-[10px] tracking-wider text-[var(--color-ink-muted)]">{TIME_LABEL[view.kind]}</div>
      {view.dateTime ? (
        <time className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]" dateTime={view.dateTime}>
          {view.primary}
        </time>
      ) : (
        <div className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{view.primary}</div>
      )}
      {view.secondary && <div className="mt-0.5 text-[11px] text-[var(--color-ink-muted)]">{view.secondary}</div>}
    </div>
  )
}
