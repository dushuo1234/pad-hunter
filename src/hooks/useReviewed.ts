import { useSyncExternalStore } from 'react'
import { getReviewedMarks, getReviewedServerMarks, subscribeReviewed, type ReviewMark } from '../utils/reviewed'

export function useReviewedMarks(): Record<string, ReviewMark> {
  return useSyncExternalStore(subscribeReviewed, getReviewedMarks, getReviewedServerMarks)
}
