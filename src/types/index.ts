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
}

export interface CandidatesPayload {
  generated_at_utc?: string
  goal?: string
  method?: Record<string, unknown>
  candidates: Candidate[]
}

export type SortKey = 'score' | 'followers' | 'kol_followers'

export interface Filters {
  search: string
  chain: string
  minFollowers: number
  minKol: number
  sort: SortKey
}
