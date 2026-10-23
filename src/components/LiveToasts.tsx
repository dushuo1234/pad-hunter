import { useEffect } from 'react'
import { useSyncExternalStore } from 'react'
import { dismissNotice, getNotices, getServerNotices, subscribeNotices } from '../utils/notices'

export function LiveToasts() {
  const notices = useSyncExternalStore(subscribeNotices, getNotices, getServerNotices)
  useEffect(() => {
    if (notices.length === 0) return
    const timers = notices.map((notice) => window.setTimeout(() => dismissNotice(notice.id), 4200))
    return () => {
      for (const timer of timers) window.clearTimeout(timer)
    }
  }, [notices])
  if (notices.length === 0) return null
  return (
    <div className="pointer-events-none fixed bottom-4 left-4 z-[70] flex w-[min(100vw-2rem,18rem)] flex-col gap-2">
      {notices.map((notice) => (
        <p
          key={notice.id}
          role="status"
          className="pointer-events-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-card)] px-3 py-2 text-sm font-medium text-[var(--color-ink)] shadow-lg dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-ink)]"
        >
          {notice.text}
        </p>
      ))}
    </div>
  )
}
