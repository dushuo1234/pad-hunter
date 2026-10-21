import { useSyncExternalStore } from 'react'
import { appPath } from '../router'
import {
  dismissToast,
  getAlertUi,
  pressSoundToggle,
  previewAlertSound,
  subscribeAlertUi,
} from '../utils/caAlert'

const BUTTON =
  'rounded-lg border px-2.5 py-1.5 text-xs font-medium transition hover:border-[var(--color-orange)]'

export function SoundAlertControls() {
  const { enabled, unlocked } = useSyncExternalStore(subscribeAlertUi, getAlertUi, getAlertUi)
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <button
        type="button"
        aria-pressed={enabled}
        aria-describedby={unlocked ? undefined : 'sound-unlock-hint'}
        onClick={pressSoundToggle}
        className={`${BUTTON} ${
          enabled
            ? 'border-[var(--color-orange)] bg-[var(--color-orange-soft)] text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.14)] dark:text-[var(--color-orange)]'
            : 'border-[var(--color-line)] bg-[var(--color-card)] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]'
        }`}
      >
        🔔 声音提示
      </button>
      {!unlocked && (
        <span id="sound-unlock-hint" className="text-[10px] font-medium text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]">
          点一下开启声音
        </span>
      )}
      <button
        type="button"
        onClick={previewAlertSound}
        className={`${BUTTON} border-[var(--color-line)] bg-[var(--color-card)] text-[var(--color-ink-soft)] hover:text-[var(--color-orange-deep)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]`}
      >
        试听
      </button>
    </div>
  )
}

export function CaAlertToasts() {
  const { toasts } = useSyncExternalStore(subscribeAlertUi, getAlertUi, getAlertUi)
  if (toasts.length === 0) return null
  return (
    <div className="pointer-events-none fixed right-4 bottom-4 z-[60] flex w-[min(100vw-2rem,22rem)] flex-col gap-2">
      {toasts.map((toast) => (
        <article
          key={toast.id}
          role="status"
          aria-live="polite"
          className="ca-toast-in pointer-events-auto relative overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-3 pr-8 shadow-[0_12px_40px_rgba(26,22,18,0.12)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]"
        >
          <span className="absolute inset-y-0 left-0 w-1 bg-[var(--color-orange)]" aria-hidden="true" />
          <p className="pl-2 font-mono text-[10px] tracking-[0.16em] text-[var(--color-orange)]">{toast.statusZh || '新CA'}</p>
          {toast.provenanceZh && (
            <p className="mt-1 pl-2 text-[11px] font-medium text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
              {toast.provenanceZh}
            </p>
          )}
          <p className="mt-1 pl-2 text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{toast.project}</p>
          <p className="mt-1 pl-2 font-mono text-[12px] break-all text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
            {toast.address}
          </p>
          <a href={appPath('ca')} className="mt-2 inline-block pl-2 font-mono text-[11px] text-[var(--color-orange)] hover:underline">
            打开发现CA
          </a>
          <button
            type="button"
            aria-label="关闭提示"
            onClick={() => dismissToast(toast.id)}
            className="absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded-md text-[var(--color-ink-muted)] hover:bg-[var(--color-cream-2)] hover:text-[var(--color-ink)] dark:hover:bg-[var(--color-night-2)] dark:hover:text-[var(--color-night-ink)]"
          >
            ×
          </button>
        </article>
      ))}
    </div>
  )
}
