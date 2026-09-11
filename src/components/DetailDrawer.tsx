import type { ReactNode } from 'react'
import type { Candidate } from '../types'
import { formatNumber, xProfileUrl } from '../utils/format'

interface DetailDrawerProps {
  candidate: Candidate | null
  onClose: () => void
}

export function DetailDrawer({ candidate, onClose }: DetailDrawerProps) {
  if (!candidate) return null
  const c = candidate

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        aria-label="关闭"
        className="backdrop-enter absolute inset-0 bg-black/40"
        onClick={onClose}
      />
      <aside className="drawer-enter relative flex h-full w-full max-w-md flex-col border-l border-[var(--color-line)] bg-[var(--color-cream)] shadow-2xl dark:border-[var(--color-night-line)] dark:bg-[var(--color-night)]">
        <div className="flex items-start justify-between gap-3 border-b border-[var(--color-line)] px-5 py-4 dark:border-[var(--color-night-line)]">
          <div>
            <div className="font-mono text-[11px] uppercase tracking-wider text-[var(--color-orange)]">
              Rank #{c.rank} · Score {c.score}
            </div>
            <h2 className="mt-1 text-xl font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
              {c.name}
            </h2>
            <a
              href={xProfileUrl(c.handle)}
              target="_blank"
              rel="noreferrer"
              className="font-mono text-sm text-[var(--color-ink-muted)] hover:text-[var(--color-orange)]"
            >
              @{c.handle}
            </a>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--color-line)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)]"
            aria-label="关闭面板"
          >
            ✕
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
          <div className="grid grid-cols-3 gap-2">
            <Metric label="粉丝" value={formatNumber(c.followers)} />
            <Metric label="KOL" value={String(c.kol_followers)} />
            <Metric label="链" value={c.chain} />
          </div>

          <Section title="为什么值得关注">
            <p className="text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
              {c.why}
            </p>
          </Section>

          {c.bio && (
            <Section title="Bio">
              <p className="text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
                {c.bio}
              </p>
            </Section>
          )}

          {c.notes && (
            <Section title="备注">
              <p className="text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
                {c.notes}
              </p>
            </Section>
          )}
        </div>

        <div className="flex gap-2 border-t border-[var(--color-line)] px-5 py-4 dark:border-[var(--color-night-line)]">
          <a
            href={xProfileUrl(c.handle)}
            target="_blank"
            rel="noreferrer"
            className="flex-1 rounded-xl bg-[var(--color-orange)] py-2.5 text-center text-sm font-semibold text-white transition hover:bg-[var(--color-orange-deep)]"
          >
            打开 X 主页
          </a>
          {c.tweet_url && (
            <a
              href={c.tweet_url}
              target="_blank"
              rel="noreferrer"
              className="flex-1 rounded-xl border border-[var(--color-line)] py-2.5 text-center text-sm font-semibold text-[var(--color-ink)] transition hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-ink)]"
            >
              相关推文
            </a>
          )}
        </div>
      </aside>
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-card)] px-3 py-3 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
      <div className="truncate font-mono text-sm font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
        {value}
      </div>
      <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
        {label}
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
        {title}
      </h3>
      {children}
    </section>
  )
}
