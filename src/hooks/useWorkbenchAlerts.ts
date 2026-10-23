import { useSyncExternalStore } from 'react'
import {
  getServerWorkbenchAlertSnapshot,
  getWorkbenchAlertSnapshot,
  subscribeWorkbenchAlerts,
} from '../utils/workbenchAlertStore'

export function useWorkbenchAlerts() {
  return useSyncExternalStore(subscribeWorkbenchAlerts, getWorkbenchAlertSnapshot, getServerWorkbenchAlertSnapshot)
}
