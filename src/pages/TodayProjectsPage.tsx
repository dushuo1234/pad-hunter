import { useEffect, useMemo, useState } from 'react'
import { WorkbenchAlertConsole } from '../components/WorkbenchAlertConsole'
import { WorkbenchAlertToasts } from '../components/WorkbenchAlertToasts'
import { useWorkbenchAlerts } from '../hooks/useWorkbenchAlerts'
import { appPath, monitorPath } from '../router'
import { formatShanghai, xProfileUrl } from '../utils/format'
import {
  countdownLabel,
  shanghaiListingLabel,
  todayProjectContacts,
  todayProjectsToShow,
  type TodayProject,
  type TodayProjectsDocument,
} from '../utils/todayProjects'
import { handleKey } from '../utils/workbench'
import { dismissWorkbenchToast, markWorkbenchAlertsRead, type WorkbenchToast } from '../utils/workbenchAlertStore'
import { alertsByHandle, workbenchRowDomId, type ProjectContact, type WorkbenchAlert } from '../utils/workbenchAlerts'

interface TodayProjectsPageProps {
  projects: TodayProjectsDocument | null
  loading: boolean
}

const LINK = 'font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline'

export function TodayProjectsPage({ projects, loading }: TodayProjectsPageProps) {
  const items = todayProjectsToShow(projects)
  const alertFeed = useWorkbenchAlerts()
  const alertsByProject = useMemo(() => alertsByHandle(alertFeed.alerts), [alertFeed.alerts])
  const contacts = useMemo(() => todayProjectContacts(items), [items])
  const handles = useMemo(() => new Set(items.map((item) => handleKey(item.handle)).filter(Boolean)), [items])
  const toasts = alertFeed.toasts.filter((toast) => handles.has(handleKey(toast.handle)))
  const generated = projects?.generated_at
  const updated = generated ? formatShanghai(generated) || generated : ''

  const openAlert = (toast: WorkbenchToast) => {
    dismissWorkbenchToast(toast.id)
    markWorkbenchAlertsRead(toast.handle)
    const id = workbenchRowDomId(toast.handle)
    if (!id) return
    window.requestAnimationFrame(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    })
  }

  return (
    <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <a href={appPath('workbench')} className="font-mono text-[11px] text-[var(--color-ink-muted)] hover:text-[var(--color-orange)]">
        ← 返回工作台
      </a>
      <div className="mt-4 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">48 小时内开盘</p>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
            今日项目清单
          </h1>
        </div>
        {items.length > 0 && (
          <p className="font-mono text-[11px] text-[var(--color-ink-muted)]">
            {items.length} 个{updated ? ` · 更新 ${updated}` : ''}
          </p>
        )}
      </div>

      {items.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          {loading ? '加载今日项目清单…' : '今日没有项目'}
        </div>
      ) : (
        <ul className="mt-6 space-y-4">
          {items.map((item, index) => (
            <TodayListCard
              key={`${item.handle}-${item.listing_at ?? ''}-${index}`}
              item={item}
              alerts={item.handle ? alertsByProject.get(handleKey(item.handle)) ?? [] : []}
              readIds={alertFeed.readIds}
              contacts={contacts}
            />
          ))}
        </ul>
      )}

      <WorkbenchAlertToasts toasts={toasts} onOpen={openAlert} onDismiss={dismissWorkbenchToast} />
    </main>
  )
}

function TodayListCard({
  item,
  alerts,
  readIds,
  contacts,
}: {
  item: TodayProject
  alerts: readonly WorkbenchAlert[]
  readIds: ReadonlySet<string>
  contacts: ReadonlyMap<string, ProjectContact>
}) {
  const summary = item.playbook?.summary?.trim() ?? ''
  const profile = item.handle ? xProfileUrl(item.handle) : ''
  return (
    <li id={workbenchRowDomId(item.handle) || undefined} className="w-full min-w-0">
      <article className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] px-4 py-4 shadow-[inset_3px_0_0_var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
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
                <h2 className="truncate text-[15px] font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{item.name}</h2>
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
          </div>
          <ListingClock item={item} />
        </div>
        {summary && (
          <p className="mt-3 text-sm leading-relaxed text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{summary}</p>
        )}
        {(item.site || item.tweet_url) && (
          <p className="mt-3 flex flex-wrap gap-3">
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
      </article>
      {item.handle ? (
        <WorkbenchAlertConsole
          alerts={alerts}
          readIds={readIds}
          name={item.name}
          handle={item.handle}
          contacts={contacts}
        />
      ) : null}
    </li>
  )
}

function ListingClock({ item }: { item: TodayProject }) {
  const label = shanghaiListingLabel(item)
  const live = Boolean(item.listing_at) && !Number.isNaN(Date.parse(item.listing_at ?? ''))
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    if (!live) return
    const id = window.setInterval(() => setNow(new Date()), 1000)
    return () => window.clearInterval(id)
  }, [live])
  if (!label) return null
  const countdown = live ? countdownLabel(item.listing_at, now) : null
  return (
    <div className="shrink-0 text-right">
      <div className="font-mono text-[10px] tracking-wider text-[var(--color-ink-muted)]">开盘时间 · 上海</div>
      {label.dateTime ? (
        <time className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]" dateTime={label.dateTime}>
          {label.text}
        </time>
      ) : (
        <div className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{label.text}</div>
      )}
      {countdown && <div className="mt-0.5 font-mono text-[11px] text-[var(--color-ink-muted)]">{countdown}</div>}
    </div>
  )
}
