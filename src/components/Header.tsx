import type { ReactNode } from 'react'
import type { AppRoute } from '../router'
import { appPath } from '../router'

interface HeaderProps {
  theme: 'light' | 'dark'
  route: AppRoute
  todayCount: number | null
  launchedCount: number | null
  onToggleTheme: () => void
  onUpload: (file: File) => void
  onRefresh: () => void
}

export function Header({ theme, route, todayCount, launchedCount, onToggleTheme, onUpload, onRefresh }: HeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-line)] bg-[color-mix(in_srgb,var(--color-cream)_88%,transparent)] backdrop-blur-md dark:border-[var(--color-night-line)] dark:bg-[color-mix(in_srgb,var(--color-night)_88%,transparent)]">
      <div className="mx-auto flex min-h-14 max-w-6xl flex-wrap items-center justify-between gap-x-3 gap-y-2 px-4 py-2 sm:px-6">
        <div className="flex min-w-0 items-center gap-3">
          <a href={appPath()} className="flex shrink-0 items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--color-orange)] shadow-[0_0_0_3px_rgba(232,135,58,0.25)]" />
            <span className="text-base font-bold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
              台子雷达
            </span>
            <span className="hidden text-sm font-medium text-[var(--color-ink-muted)] sm:inline">/ Pad Hunter</span>
          </a>
          <nav className="flex items-center gap-1" aria-label="主导航">
            <NavLink href={appPath()} active={route.name === 'home'}>
              项目
            </NavLink>
            <NavLink href={appPath('today')} active={route.name === 'today'}>
              即将开盘
              {todayCount != null && todayCount > 0 && (
                <span className="font-mono text-[10px] opacity-80">{todayCount}</span>
              )}
            </NavLink>
            <NavLink href={appPath('launched')} active={route.name === 'launched'}>
              已开盘
              {launchedCount != null && (
                <span className="font-mono text-[10px] opacity-80">{launchedCount}</span>
              )}
            </NavLink>
            <NavLink href={appPath('workbench')} active={route.name === 'workbench'}>
              工作台
            </NavLink>
          </nav>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={onRefresh}
            className="rounded-lg border border-[var(--color-line)] bg-[var(--color-card)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-ink-soft)] transition hover:border-[var(--color-orange)] hover:text-[var(--color-orange-deep)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)] dark:hover:border-[var(--color-orange)]"
          >
            刷新
          </button>
          <label className="cursor-pointer rounded-lg border border-[var(--color-line)] bg-[var(--color-card)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-ink-soft)] transition hover:border-[var(--color-orange)] hover:text-[var(--color-orange-deep)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)] dark:hover:border-[var(--color-orange)]">
            上传 JSON
            <input
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0]
                if (f) onUpload(f)
                e.target.value = ''
              }}
            />
          </label>

          <button
            type="button"
            onClick={onToggleTheme}
            aria-label="切换主题"
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-line)] bg-[var(--color-card)] text-[var(--color-ink-soft)] transition hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]"
          >
            {theme === 'dark' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="4" />
                <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 14.5A8.5 8.5 0 1 1 9.5 3 7 7 0 0 0 21 14.5z" />
              </svg>
            )}
          </button>
        </div>
      </div>
    </header>
  )
}

function NavLink({ href, active, children }: { href: string; active: boolean; children: ReactNode }) {
  return (
    <a
      href={href}
      aria-current={active ? 'page' : undefined}
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium transition ${
        active
          ? 'bg-[var(--color-orange)] text-white'
          : 'text-[var(--color-ink-soft)] hover:bg-[var(--color-orange-soft)] hover:text-[var(--color-orange-deep)] dark:text-[var(--color-night-soft)] dark:hover:bg-[rgba(232,135,58,0.12)] dark:hover:text-[var(--color-orange)]'
      }`}
    >
      {children}
    </a>
  )
}
