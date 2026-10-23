import { useState } from 'react'
import { shortAddr } from '../utils/format'
import { ALERT_UI, reminderViews, type WorkbenchAlert } from '../utils/workbenchAlerts'

export function WorkbenchReminders({ alerts, now }: { alerts: readonly WorkbenchAlert[]; now: number }) {
  const views = reminderViews(alerts, now)
  const [copied, setCopied] = useState('')
  const [openQuote, setOpenQuote] = useState<string | null>(null)
  if (views.length === 0) return null

  const copyAddress = async (address: string) => {
    try {
      await navigator.clipboard.writeText(address)
    } catch {
      const input = document.createElement('textarea')
      input.value = address
      input.setAttribute('readonly', '')
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    setCopied(address)
    window.setTimeout(() => setCopied((current) => (current === address ? '' : current)), 1500)
  }

  return (
    <ul className="mt-1 space-y-1" aria-label="项目提醒">
      {views.map((view) => {
        const quoteOpen = openQuote === view.key
        return (
          <li key={view.key} className="flex items-start gap-1.5 text-[11px] leading-snug" title={view.quote || undefined}>
            <span aria-hidden="true" className="shrink-0">
              {view.mark}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1">
                {view.label && (
                  <span className="font-medium text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{view.label}</span>
                )}
                {view.badge && <CaBadge label={view.badge.label} tone={view.badge.tone} />}
                {view.delay && (
                  <span className="inline-flex items-center rounded-md bg-rose-600 px-1.5 py-0.5 text-[10px] font-semibold text-white">
                    {ALERT_UI.delay}
                  </span>
                )}
                {view.address && (
                  <span className="font-mono text-[10px] text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]" title={view.address}>
                    {shortAddr(view.address)}
                  </span>
                )}
                {view.copyable && (
                  <button
                    type="button"
                    onClick={() => void copyAddress(view.address)}
                    className="rounded-md px-1 text-[10px] font-medium text-[var(--color-orange)] hover:underline"
                  >
                    {copied === view.address ? ALERT_UI.copied : ALERT_UI.copy}
                  </button>
                )}
                {view.chain && (
                  <span className="text-[10px] text-[var(--color-ink-muted)]">{view.chain}</span>
                )}
              </div>
              {view.body && (
                <p className="mt-0.5 break-words text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">{view.body}</p>
              )}
              {(view.quote || view.evidenceUrl) && (
                <div className="mt-0.5">
                  {view.quote && (
                    <button
                      type="button"
                      aria-expanded={quoteOpen}
                      onClick={() => setOpenQuote((current) => (current === view.key ? null : view.key))}
                      className="text-[10px] text-[var(--color-orange)] hover:underline"
                    >
                      {ALERT_UI.source}
                    </button>
                  )}
                  {quoteOpen && view.quote && (
                    <p className="mt-0.5 whitespace-pre-wrap break-words text-[10px] text-[var(--color-ink-muted)]">{view.quote}</p>
                  )}
                  {view.evidenceUrl && (
                    <a
                      href={view.evidenceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className={`${view.quote ? 'ml-2' : ''} text-[10px] text-[var(--color-orange)] hover:underline`}
                    >
                      {ALERT_UI.source}
                    </a>
                  )}
                </div>
              )}
            </div>
            {view.ago && (
              <time dateTime={view.ts || undefined} className="shrink-0 text-[10px] text-[var(--color-ink-muted)]">
                {view.ago}
              </time>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function CaBadge({ label, tone }: { label: string; tone: 'ok' | 'warn' | 'muted' }) {
  const toneClass =
    tone === 'ok'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
      : tone === 'warn'
        ? 'bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200'
        : 'bg-[var(--color-cream-2)] text-[var(--color-ink-muted)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-muted)]'
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold ${toneClass}`}>{label}</span>
}
