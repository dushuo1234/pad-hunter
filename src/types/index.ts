export interface Candidate {
  rank: number
  handle: string
  name: string
  /** Numeric follower count, or a raw fans string such as `粉丝 188 · 你圈子 1 人`. */
  followers: number | string
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
  /** Channel id, e.g. `telegram:项目推送` or `telegram:项目推送监控`. */
  source?: string
  ca?: string | null
  ca_chain?: string | null
  ca_source?: string | null
  listing_signal?: string | null
  sites?: string[]
  last_checked?: string
  onchain_notes?: string
}

export interface CandidatesPayload {
  generated_at_utc?: string
  goal?: string
  /** Legacy single source. Per-candidate `source` wins when both are set. */
  source?: string
  sources?: string[]
  method?: Record<string, unknown>
  candidates: Candidate[]
}

export type SortKey = 'date' | 'score' | 'followers' | 'kol_followers'

export interface Filters {
  search: string
  chain: string
  category: string
  source: string
  minFollowers: number
  minKol: number
  sort: SortKey
}

/** Site probe. Same fields as `latest.json` results and listing-scan `sites[]`. */
export interface SiteProbe {
  url: string
  status?: string
  ok?: boolean
  http_code?: string | number
  time_s?: number
  final_url?: string
  error?: string
  name?: string
  handle?: string
}

/** Listing signal. Same fields as `listing_scan_latest.json` `new_listing_signals[]`. */
export interface ListingSignal {
  name?: string
  handle?: string
  signal: string
  prev?: string | null
  keyword?: string
  source?: string
}

/** On-chain factory deploy. Scanner output can use this object under `factory_deploy`. */
export interface FactoryDeploy {
  chain?: string
  tx?: string
  factory?: string
  token?: string
  block?: number | null
  notes?: string
  name?: string
  handle?: string
}

export type MonitorKind = 'site' | 'listing_signal' | 'ca' | 'factory'

/**
 * One monitor timeline row.
 * `kind: "site"` carries a `site` probe, `listing_signal` carries the signal object,
 * `ca` uses the watchlist fields `ca` / `ca_chain` / `ca_source`, and `factory`
 * carries `factory_deploy`. `sample: true` is demo data and is not treated as a live CA.
 */
export interface MonitorEvent {
  id: string
  kind: MonitorKind
  at: string
  handle: string
  name: string
  sample?: boolean
  note?: string
  site?: SiteProbe
  listing_signal?: ListingSignal
  ca?: string | null
  ca_chain?: string | null
  ca_source?: string | null
  factory_deploy?: FactoryDeploy
}

export interface MonitorDocument {
  events: MonitorEvent[]
  generatedAt?: string
  note?: string
  files: string[]
}
