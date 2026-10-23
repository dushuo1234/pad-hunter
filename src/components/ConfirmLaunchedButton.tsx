import { useState } from 'react'
import { useSyncExternalStore } from 'react'
import type { Candidate } from '../types'
import { confirmManualLaunch } from '../utils/boardSync'
import { getApiSettings, subscribeApiSettings, type ApiSettings } from '../utils/workbenchApi'

const SERVER_SETTINGS: ApiSettings = { token: '', baseUrl: '' }

interface ConfirmLaunchedButtonProps {
  candidate?: Candidate | null
  handle?: string
  name?: string
  variant?: 'button' | 'compact' | 'link'
  className?: string
}

export function ConfirmLaunchedButton({
  candidate,
  handle,
  name,
  variant = 'button',
  className = '',
}: ConfirmLaunchedButtonProps) {
  const settings = useSyncExternalStore(subscribeApiSettings, getApiSettings, () => SERVER_SETTINGS)
  const token = settings.token.trim()
  const resolvedHandle = candidate?.handle || handle || ''
  const resolvedName = candidate?.name || name || resolvedHandle
  const [open, setOpen] = useState(false)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  if (!resolvedHandle.replace(/^@/, '').trim()) return null

  const ask = (event: { stopPropagation: () => void; preventDefault: () => void }) => {
    event.stopPropagation()
    event.preventDefault()
    if (!token || pending) return
    setError(null)
    setOpen(true)
  }

  const close = () => {
    if (pending) return
    setOpen(false)
    setError(null)
  }

  const confirm = async () => {
    setPending(true)
    setError(null)
    const message = await confirmManualLaunch({ handle: resolvedHandle, name: resolvedName })
    setPending(false)
    if (message) {
      setError(message)
      return
    }
    setOpen(false)
  }

  const hint = '请先设置同步口令'
  const buttonClass =
    variant === 'link'
      ? `text-xs font-medium text-[var(--color-orange)] hover:underline disabled:cursor-not-allowed disabled:opacity-60 disabled:no-underline ${className}`
      : variant === 'compact'
        ? `inline-flex items-center justify-center rounded-md border border-[var(--color-line)] bg-[var(--color-card)] px-2 py-1 text-[11px] font-medium text-[var(--color-ink)] hover:border-[var(--color-orange)] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-ink)] ${className}`
        : `inline-flex items-center justify-center rounded-lg border border-[var(--color-line)] px-3 py-2 text-sm font-medium text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] disabled:cursor-not-allowed disabled:opacity-60 dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)] ${className}`

  return (
    <>
      <button
        type="button"
        disabled={!token || pending}
        title={token ? '确认已开盘，并从其他分组移入已开盘' : hint}
        onClick={ask}
        onKeyDown={(event) => event.stopPropagation()}
        className={buttonClass}
      >
        确认已开盘
      </button>
      {!token && variant === 'button' && (
        <p className="mt-1 text-center text-[11px] text-[var(--color-ink-muted)]">{hint}</p>
      )}
      {open && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 px-4"
          onMouseDown={(event) => {
            event.stopPropagation()
            if (event.target === event.currentTarget) close()
          }}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-launched-title"
            onMouseDown={(event) => event.stopPropagation()}
            className="w-full max-w-sm rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 shadow-xl dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]"
          >
            <h2 id="confirm-launched-title" className="text-base font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
              确认已开盘并移除？
            </h2>
            <p className="mt-2 text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
              「{resolvedName}」会离开工作台，并从即将开盘、项目推送和其他分组里移出，记入已开盘。其他打开的页面会一起更新。
            </p>
            {error && <p className="mt-2 text-xs text-rose-700 dark:text-rose-300">{error}</p>}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={close}
                disabled={pending}
                className="rounded-lg px-3 py-1.5 text-sm text-[var(--color-ink-soft)] hover:bg-[var(--color-cream-2)] disabled:opacity-60 dark:text-[var(--color-night-soft)] dark:hover:bg-[var(--color-night-2)]"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void confirm()}
                disabled={pending}
                className="rounded-lg bg-[var(--color-orange)] px-3 py-1.5 text-sm font-semibold text-white hover:bg-[var(--color-orange-deep)] disabled:opacity-60"
              >
                {pending ? '提交中' : '确认已开盘'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
