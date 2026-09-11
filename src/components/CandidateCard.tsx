import type { ReactNode } from 'react'
import type { Candidate } from '../types'
import { formatNumber, xProfileUrl } from '../utils/format'

interface CandidateCardProps {
  candidate: Candidate
  onOpen: (c: Candidate) => void
}

export function CandidateCard({ candidate: c, onOpen }: CandidateCardProps) {
  return (
    <article
      role="button"
      tabIndex={0}
      onClick={() => onOpen(c)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(c)
        }
      }}
      className="group cursor-pointer rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 shadow-sm transition hover:-translate-y-0.5 hover:border-[var(--color-orange)] hover:shadow-md dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:hover:border-[var(--color-orange)] sm:p-5"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-orange-soft)] font-mono text-sm font-bold text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]">
            #{c.rank}
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-semibold text-[var(--color-ink)] group-hover:text-[var(--color-orange-deep)] dark:text-[var(--color-night-ink)] dark:group-hover:text-[var(--color-orange)]">
              {c.name}
            </h3>
            <a
              href={xProfileUrl(c.handle)}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="font-mono text-xs text-[var(--color-ink-muted)] hover:text-[var(--color-orange)]"
            >
              @{c.handle}
            </a>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <div className="font-mono text-lg font-bold text-[var(--color-orange)]">{c.score}</div>
          <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
            Score
          </div>
        </div>
      </div>

      <p className="mt-3 line-clamp-2 text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        {c.why}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Chip>{c.chain}</Chip>
        <Chip mono>{formatNumber(c.followers)} 粉丝</Chip>
        <Chip mono>{c.kol_followers} KOL</Chip>
        {c.tweet_url && (
          <a
            href={c.tweet_url}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="ml-auto font-mono text-[11px] text-[var(--color-orange)] hover:underline"
          >
            查看推文 →
          </a>
        )}
      </div>
    </article>
  )
}

function Chip({
  children,
  mono,
}: {
  children: ReactNode
  mono?: boolean
}) {
  return (
    <span
      className={`rounded-md border border-[var(--color-line)] bg-[var(--color-cream-2)] px-2 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)] ${
        mono ? 'font-mono' : 'font-medium'
      }`}
    >
      {children}
    </span>
  )
}
