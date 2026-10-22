import { formatPushDate, resolvePushDate, UNKNOWN_PUSH_DATE } from '../utils/pushDate'

interface PushDateProps {
  records: readonly unknown[]
  /** `line` prefixes 推送日期. `value` is only the date, for a column that already has that header. */
  variant?: 'line' | 'value'
  className?: string
}

export function PushDate({ records, variant = 'line', className }: PushDateProps) {
  const stamp = resolvePushDate(records)
  const text = stamp ? formatPushDate(stamp) || UNKNOWN_PUSH_DATE : UNKNOWN_PUSH_DATE
  const title = stamp ? `来源 ${stamp.field}` : '没有可用的推送时间'
  const body = stamp && text !== UNKNOWN_PUSH_DATE ? <time dateTime={stamp.at}>{text}</time> : text

  if (variant === 'value') {
    return (
      <span className={className ?? 'font-mono text-xs text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]'} title={title}>
        {body}
      </span>
    )
  }

  return (
    <span
      className={
        className ??
        'font-mono text-[11px] text-[var(--color-ink-muted)]'
      }
      title={title}
    >
      推送日期 {body}
    </span>
  )
}
