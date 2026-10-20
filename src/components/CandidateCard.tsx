import type { ReactNode } from 'react'
import type { Candidate } from '../types'
import { monitorPath } from '../router'
import { PinWorkbenchButton } from './PinWorkbenchButton'
import { SourceBadge } from './SourceBadge'
import { categoryOf } from '../utils/categories'
import { followerCount, formatNumber, formatShanghai, sameXUrl, xProfileUrl } from '../utils/format'
import { formatLaunchLabel, listingSourceLabel, structuredLaunch } from '../utils/launch'

interface CandidateCardProps {
  candidate: Candidate
  onOpen: (c: Candidate) => void
  compact?: boolean
}

export function CandidateCard({ candidate: c, onOpen, compact = false }: CandidateCardProps) {
  const profile = xProfileUrl(c.handle)
  const link = c.tweet_url || profile
  const isTweet = Boolean(c.tweet_url) && !sameXUrl(c.tweet_url, profile)
  const when = formatShanghai(c.date_iso)
  const followers = followerCount(c.followers)
  const launch = structuredLaunch(c)
  const launchSource = launch ? listingSourceLabel(launch.source) : ''

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
      className={`group cursor-pointer rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] shadow-sm transition hover:-translate-y-0.5 hover:border-[var(--color-orange)] hover:shadow-md dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:hover:border-[var(--color-orange)] ${
        compact ? 'p-3.5' : 'p-4 sm:p-5'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {!compact && (
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--color-orange-soft)] font-mono text-sm font-bold text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]">
              #{c.rank}
            </div>
          )}
          <div className="min-w-0">
            <h3 className="truncate text-[15px] font-semibold text-[var(--color-ink)] group-hover:text-[var(--color-orange-deep)] dark:text-[var(--color-night-ink)] dark:group-hover:text-[var(--color-orange)]">
              {c.name}
            </h3>
            <a
              href={profile}
              target="_blank"
              rel="noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="font-mono text-xs text-[var(--color-ink-muted)] hover:text-[var(--color-orange)]"
            >
              @{c.handle}
            </a>
          </div>
        </div>

        {compact ? (
          <div className="shrink-0 text-right">
            <div className="font-mono text-[10px] text-[var(--color-ink-muted)]">#{c.rank}</div>
            {when && (
              <time className="font-mono text-[10px] text-[var(--color-ink-muted)]" dateTime={c.date_iso}>
                {when}
              </time>
            )}
          </div>
        ) : (
          <div className="shrink-0 text-right">
            <div className="font-mono text-lg font-bold text-[var(--color-orange)]">{c.score}</div>
            <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
              Score
            </div>
          </div>
        )}
      </div>

      <p
        className={`mt-3 text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)] ${
          compact ? 'line-clamp-3' : 'line-clamp-2'
        }`}
      >
        {c.why}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <SourceBadge source={c.source} />
        <Chip tone="accent">{categoryOf(c)}</Chip>
        <Chip>{c.chain}</Chip>
        {c.status && <Chip>{c.status}</Chip>}
        {c.listing && <Chip>{c.listing}</Chip>}
        {launch && (
          <Chip tone="accent" title={launchSource ? `来源 ${launchSource}` : undefined}>
            开盘 {formatLaunchLabel(launch)}
            {launchSource ? ` · ${launchSource}` : ''}
          </Chip>
        )}
        {c.risk && (
          <Chip tone="warn" title={c.risk}>
            风险
          </Chip>
        )}
        {followers > 0 && <Chip mono>{formatNumber(followers)} 粉丝</Chip>}
        {c.kol_followers > 0 && <Chip mono>{c.kol_followers} KOL</Chip>}
        {!compact && when && (
          <time className="font-mono text-[11px] text-[var(--color-ink-muted)]" dateTime={c.date_iso}>
            {when}
          </time>
        )}
        <span className="ml-auto flex items-center gap-3">
          <a
            href={monitorPath(c.handle)}
            onClick={(e) => e.stopPropagation()}
            className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline"
          >
            监控详情
          </a>
          <a
            href={link}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="font-mono text-[11px] text-[var(--color-orange)] hover:underline"
          >
            {isTweet ? '查看推文 →' : '打开 X →'}
          </a>
        </span>
      </div>

      <div className="mt-3 border-t border-[var(--color-line)] pt-3 dark:border-[var(--color-night-line)]">
        <PinWorkbenchButton candidate={c} variant="button" className="w-full" />
      </div>
    </article>
  )
}

function Chip({
  children,
  mono,
  tone = 'default',
  title,
}: {
  children: ReactNode
  mono?: boolean
  tone?: 'default' | 'accent' | 'warn'
  title?: string
}) {
  const toneClass =
    tone === 'accent'
      ? 'border-transparent bg-[var(--color-orange-soft)] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]'
      : tone === 'warn'
        ? 'border-transparent bg-[var(--color-orange-soft)] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.12)] dark:text-[var(--color-orange)]'
        : 'border-[var(--color-line)] bg-[var(--color-cream-2)] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]'

  return (
    <span
      title={title}
      className={`rounded-md border px-2 py-0.5 text-[11px] ${toneClass} ${mono ? 'font-mono' : ''}`}
    >
      {children}
    </span>
  )
}
