export interface Candidate {
  rank: number
  handle: string
  name: string
  followers: number
  kol_followers: number
  bio: string
  why: string
  score: number
  tweet_url: string
  chain: string
  notes?: string
  category?: string
  status?: string
  listing?: string
  risk?: string
  message_id?: number
  date_iso?: string
}

export interface CandidatesPayload {
  generated_at_utc?: string
  goal?: string
  source?: string
  method?: Record<string, unknown>
  candidates: Candidate[]
}

export type SortKey = 'date' | 'score' | 'followers' | 'kol_followers'

export interface Filters {
  search: string
  chain: string
  category: string
  minFollowers: number
  minKol: number
  sort: SortKey
}
