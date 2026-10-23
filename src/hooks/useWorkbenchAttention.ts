import { useMemo } from 'react'
import { handleKey } from '../utils/workbench'
import { flashingReminderCount } from '../utils/workbenchAlerts'
import { useWorkbenchAlerts } from './useWorkbenchAlerts'
import { useWorkbenchItems } from './useWorkbench'

/** Unread blinking reminders on pinned projects that are still on the workbench. */
export function useWorkbenchAttention(launchedHandles: ReadonlySet<string>): number {
  const feed = useWorkbenchAlerts()
  const items = useWorkbenchItems()
  return useMemo(() => {
    const pinned = new Set<string>()
    for (const item of items) {
      const key = handleKey(item.handle)
      if (key) pinned.add(key)
    }
    return flashingReminderCount(feed.alerts, feed.readIds, { pinned, launched: launchedHandles })
  }, [feed.alerts, feed.readIds, items, launchedHandles])
}
