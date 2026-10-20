import { sourceChannel } from '../utils/format'

export function SourceBadge({ source }: { source?: string }) {
  const channel = sourceChannel(source)
  if (!channel) return null
  const monitor = channel.includes('监控')
  const tone = monitor
    ? 'border-transparent bg-[var(--color-orange-soft)] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]'
    : 'border-[var(--color-line)] bg-[var(--color-cream-2)] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]'
  return (
    <span title={source} className={`rounded-md border px-2 py-0.5 text-[11px] ${tone}`}>
      {channel}
    </span>
  )
}
