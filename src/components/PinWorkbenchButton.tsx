import type { Candidate } from '../types'
import { useWorkbenchItems } from '../hooks/useWorkbench'
import { isHandlePinned, pinObserved } from '../utils/workbench'

interface PinWorkbenchButtonProps {
  candidate?: Candidate | null
  name?: string
  handle?: string
  variant?: 'link' | 'button'
  className?: string
}

export function PinWorkbenchButton({
  candidate,
  name,
  handle,
  variant = 'link',
  className = '',
}: PinWorkbenchButtonProps) {
  const items = useWorkbenchItems()
  const resolvedHandle = candidate?.handle || handle || ''
  const resolvedName = candidate?.name || name || resolvedHandle
  const pinned = isHandlePinned(items, resolvedHandle)
  if (!resolvedHandle && !resolvedName) return null

  const onPin = (event: { stopPropagation: () => void; preventDefault: () => void }) => {
    event.stopPropagation()
    event.preventDefault()
    pinObserved({ name: resolvedName, handle: resolvedHandle, candidate })
  }

  const label = pinned ? '已在工作台' : '加入工作台'

  if (variant === 'button') {
    return (
      <button
        type="button"
        aria-pressed={pinned}
        title={pinned ? '已钉选。再次点击会用公开资料补全空字段，备注保留' : '加入工作台'}
        onClick={onPin}
        onKeyDown={(event) => event.stopPropagation()}
        className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
          pinned
            ? 'border-[var(--color-orange)] bg-[var(--color-orange-soft)] text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.12)] dark:text-[var(--color-orange)]'
            : 'border-[var(--color-line)] bg-[var(--color-card)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] hover:text-[var(--color-orange-deep)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]'
        } ${className}`}
      >
        {label}
      </button>
    )
  }

  return (
    <button
      type="button"
      aria-pressed={pinned}
      title={pinned ? '已钉选。再次点击会用公开资料补全空字段，备注保留' : '加入工作台'}
      onClick={onPin}
      onKeyDown={(event) => event.stopPropagation()}
      className={`font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline ${className}`}
    >
      {label}
    </button>
  )
}
