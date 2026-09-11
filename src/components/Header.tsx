interface HeaderProps {
  theme: 'light' | 'dark'
  onToggleTheme: () => void
  onUpload: (file: File) => void
}

export function Header({ theme, onToggleTheme, onUpload }: HeaderProps) {
  return (
    <header className="sticky top-0 z-40 border-b border-[var(--color-line)] bg-[color-mix(in_srgb,var(--color-cream)_88%,transparent)] backdrop-blur-md dark:border-[var(--color-night-line)] dark:bg-[color-mix(in_srgb,var(--color-night)_88%,transparent)]">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-block h-2.5 w-2.5 rounded-full bg-[var(--color-orange)] shadow-[0_0_0_3px_rgba(232,135,58,0.25)]" />
            <span className="text-base font-bold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
              台子雷达
            </span>
            <span className="hidden text-sm font-medium text-[var(--color-ink-muted)] sm:inline">
              / Pad Hunter
            </span>
          </div>
          <span className="hidden rounded border border-[var(--color-line)] px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)] sm:inline">
            Launchpad Product Radar
          </span>
        </div>

        <div className="flex items-center gap-2">
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
