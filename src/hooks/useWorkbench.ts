import { useSyncExternalStore } from 'react'
import { getWorkbenchItems, subscribeWorkbench, type WorkbenchItem } from '../utils/workbench'

const EMPTY: WorkbenchItem[] = []

export function useWorkbenchItems(): WorkbenchItem[] {
  return useSyncExternalStore(subscribeWorkbench, getWorkbenchItems, () => EMPTY)
}
