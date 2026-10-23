import { useEffect, useSyncExternalStore } from 'react'
import type { Candidate } from '../types'
import {
  getBoardSyncServerStatus,
  getBoardSyncStatus,
  setBoardSyncCatalog,
  startBoardSync,
  subscribeBoardSync,
  type BoardSyncStatus,
} from '../utils/boardSync'

export function useBoardSync(candidates: Candidate[], loading: boolean) {
  useEffect(() => {
    setBoardSyncCatalog(candidates, !loading)
  }, [candidates, loading])

  useEffect(() => startBoardSync(), [])
}

export function useBoardSyncStatus(): BoardSyncStatus {
  return useSyncExternalStore(subscribeBoardSync, getBoardSyncStatus, getBoardSyncServerStatus)
}
