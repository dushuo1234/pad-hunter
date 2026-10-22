import { useReviewedMarks } from '../hooks/useReviewed'
import { reviewHasUpdate, reviewKey, toggleReviewed, type ReviewSnapshot } from '../utils/reviewed'

interface ReviewedMarkProps {
  handle?: string | null
  name?: string | null
  snapshot: ReviewSnapshot
  /** `toggle` always shows the button. `badge` only shows a mark that is already on. */
  mode?: 'toggle' | 'badge'
  className?: string
}

const BUTTON =
  'inline-flex min-h-7 items-center rounded-md border px-2 py-0.5 text-[11px] font-semibold leading-none'

export function ReviewedMark({ handle, name, snapshot, mode = 'badge', className = '' }: ReviewedMarkProps) {
  const marks = useReviewedMarks()
  const key = reviewKey(handle, name)
  const mark = key ? marks[key] : undefined
  const on = Boolean(mark)
  if (mode === 'badge' && !on) return null
  const updated = Boolean(on && mark && reviewHasUpdate(mark.snapshot, snapshot))
  const label = on ? '✓ 已看' : '标记已看'

  return (
    <span className={`inline-flex flex-wrap items-center gap-1 ${className}`} onKeyDown={(event) => event.stopPropagation()}>
      <button
        type="button"
        aria-pressed={on}
        disabled={!key}
        title={on ? '取消已看' : '标记已看'}
        onClick={(event) => {
          event.stopPropagation()
          event.preventDefault()
          if (key) toggleReviewed(key, snapshot)
        }}
        className={`${BUTTON} ${
          on
            ? 'border-[#166534] bg-[#ecfdf3] text-[#166534] dark:border-[#86efac] dark:bg-[#052e16] dark:text-[#86efac]'
            : 'border-[var(--color-line)] bg-[var(--color-cream-2)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]'
        } disabled:cursor-not-allowed disabled:opacity-50`}
      >
        {label}
      </button>
      {updated && (
        <span
          title="标记之后，开盘时间、状态、开盘或 CA 有变化"
          className="inline-flex min-h-7 items-center rounded-md border border-[#a16207] bg-[#fefce8] px-1.5 py-0.5 text-[11px] font-semibold leading-none text-[#854d0e] dark:border-[#fde68a] dark:bg-[#422006] dark:text-[#fde68a]"
        >
          有更新
        </span>
      )}
    </span>
  )
}
