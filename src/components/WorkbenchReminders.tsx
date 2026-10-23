import { useState, type ReactNode } from 'react'
import { shortAddr } from '../utils/format'
import { ALERT_UI, reminderViews, type ReminderTone, type WorkbenchAlert } from '../utils/workbenchAlerts'

const PILL: Record<ReminderTone, string> = {
  soon: 'bg-orange-600 text-white',
  ok: 'bg-emerald-600 text-white',
  warn: 'bg-amber-400 text-amber-950',
  muted: 'bg-neutral-300 text-neutral-600 dark:bg-neutral-700 dark:text-neutral-300',
  change: 'bg-sky-600 text-white',
}

export function WorkbenchReminders({
  alerts,
  now,
  readIds,
  onAcknowledge,
}: {
  alerts: readonly WorkbenchAlert[]
  now: number
  readIds: ReadonlySet<string>
  onAcknowledge?: () => void
}) {
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
    <ul className="mt-1.5 space-y-1" aria-label="项目提醒">
      {views.map((view) => {
        const quoteOpen = openQuote === view.key
        const flashing = view.urgent && !readIds.has(view.id)
        return (
          <li
            key={view.key}
            data-alert-tone={view.tone}
            title={flashing ? ALERT_UI.consoleStop : view.quote || undefined}
            onClick={
              flashing
                ? () => {
                    onAcknowledge?.()
                  }
                : undefined
            }
            className={`flex items-start gap-1.5 rounded-lg text-sm font-semibold leading-snug ${
              flashing ? 'wb-line-flash cursor-pointer px-1.5 py-1' : ''
            }`}
          >
            <span aria-hidden="true" className="shrink-0 text-base leading-none">
              {view.mark}
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                {view.label && <TonePill tone={view.tone}>{view.label}</TonePill>}
                {view.badge && <TonePill tone={view.tone}>{view.badge.label}</TonePill>}
                {view.delay && (
                  <span className="inline-flex items-center rounded-full bg-rose-600 px-2 py-0.5 text-xs font-bold text-white">
                    {ALERT_UI.delay}
                  </span>
                )}
                {view.address && (
                  <span className="font-mono text-xs text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]" title={view.address}>
                    {shortAddr(view.address)}
                  </span>
                )}
                {view.copyable && (
                  <button
                    type="button"
                    onClick={() => {
                      void copyAddress(view.address)
                    }}
                    className="rounded-full px-1.5 text-xs font-bold text-[var(--color-orange)] hover:underline"
                  >
                    {copied === view.address ? ALERT_UI.copied : ALERT_UI.copy}
                  </button>
                )}
                {view.chain && <span className="text-xs font-medium text-[var(--color-ink-muted)]">{view.chain}</span>}
              </div>
              {view.body && (
                <p className="mt-0.5 break-words text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{view.body}</p>
              )}
              {(view.quote || view.evidenceUrl) && (
                <div className="mt-0.5 font-medium">
                  {view.quote && (
                    <button
                      type="button"
                      aria-expanded={quoteOpen}
                      onClick={() => {
                        setOpenQuote((current) => (current === view.key ? null : view.key))
                      }}
                      className="text-xs text-[var(--color-orange)] hover:underline"
                    >
                      {ALERT_UI.source}
                    </button>
                  )}
                  {quoteOpen && view.quote && (
                    <p className="mt-0.5 whitespace-pre-wrap break-words text-xs font-medium text-[var(--color-ink-muted)]">{view.quote}</p>
                  )}
                  {view.evidenceUrl && (
                    <a
                      href={view.evidenceUrl}
                      target="_blank"
                      rel="noreferrer"
                      className={`${view.quote ? 'ml-2' : ''} text-xs text-[var(--color-orange)] hover:underline`}
                    >
                      {ALERT_UI.source}
                    </a>
                  )}
                </div>
              )}
            </div>
            {view.ago && (
              <time dateTime={view.ts || undefined} className="shrink-0 text-xs font-medium text-[var(--color-ink-muted)]">
                {view.ago}
              </time>
            )}
          </li>
        )
      })}
    </ul>
  )
}

function TonePill({ tone, children }: { tone: ReminderTone; children: ReactNode }) {
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-bold leading-none ${PILL[tone]}`}>
      {children}
    </span>
  )
}
