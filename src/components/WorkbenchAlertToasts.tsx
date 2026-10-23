import type { WorkbenchToast } from '../utils/workbenchAlertStore'

export function WorkbenchAlertToasts({
  toasts,
  onOpen,
  onDismiss,
}: {
  toasts: readonly WorkbenchToast[]
  onOpen: (toast: WorkbenchToast) => void
  onDismiss: (id: string) => void
}) {
  if (toasts.length === 0) return null
  return (
    <div className="pointer-events-none fixed top-4 right-4 z-[70] flex w-[min(100vw-2rem,22rem)] flex-col gap-2">
      {toasts.map((toast) => (
        <article
          key={toast.id}
          role="status"
          className="ca-toast-in pointer-events-auto relative overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] shadow-[0_12px_40px_rgba(26,22,18,0.12)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]"
        >
          <button
            type="button"
            onClick={() => onOpen(toast)}
            className="block w-full px-3 py-3 pr-8 text-left text-sm leading-snug text-[var(--color-ink)] hover:bg-[var(--color-cream)] dark:text-[var(--color-night-ink)] dark:hover:bg-[var(--color-night-2)]"
          >
            {toast.summary}
          </button>
          <button
            type="button"
            aria-label="关闭提示"
            onClick={() => onDismiss(toast.id)}
            className="absolute top-2 right-2 flex h-6 w-6 items-center justify-center rounded-md text-[var(--color-ink-muted)] hover:bg-[var(--color-cream-2)] hover:text-[var(--color-ink)] dark:hover:bg-[var(--color-night-2)] dark:hover:text-[var(--color-night-ink)]"
          >
            ×
          </button>
        </article>
      ))}
    </div>
  )
}
