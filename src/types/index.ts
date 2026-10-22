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
  /** Pipeline flag: already listed, even when the status text has not caught up. */
  already_listed?: boolean
  /** ISO-8601 launch time. `YYYY-MM-DD` is a Shanghai date with no clock. */
  listing_at?: string | null
  /** Alias of `listing_at` when a pipeline uses that name. */
  launch_at?: string | null
  /** Where the launch time was read: `site`, `x`, or `tg`. */
  listing_at_source?: string | null
  /** Link to the post or page the listing time was read from. Not a launch time. */
  listing_at_evidence_url?: string | null
  /** Pipeline mark: listing time passed and the project is still not open. */
  deferred?: boolean
  postponed?: boolean
  risk?: string
  message_id?: number
  /** Telegram message time of the push card. Not the launch time. */
  date_iso?: string
  /**
   * When this project first entered the radar. Canonical field written by
   * `scripts/telegram/sync_site.py`. The page also accepts `first_seen`,
   * `added_at`, `synced_at`, and `created_at`, and uses the earliest one.
   */
  push_date?: string | null
  first_seen?: string | null
  added_at?: string | null
  synced_at?: string | null
  created_at?: string | null
  /** Channel id, e.g. `telegram:项目推送` or `telegram:项目推送监控`. */
  source?: string
  ca?: string | null
  ca_chain?: string | null
  ca_source?: string | null
  listing_signal?: string | null
  sites?: string[]
  last_checked?: string
  onchain_notes?: string
  /**
   * Site / JS / is-file completion. A 0–1 fraction, a 0–100 score, or a label
   * such as `high` / `complete` / `完成`. See `upcomingSignals.ts`.
   * Any one of these being high puts the project on 即将开盘 when it has no listing time.
   */
  completion?: number | string | null
  site_completion?: number | string | null
  js_completion?: number | string | null
  contract_completion?: number | string | null
  contract_code?: number | string | null
  contract_code_completion?: number | string | null
  game_completion?: number | string | null
  game_code?: number | string | null
  game_code_completion?: number | string | null
  /** Nested scrape, for example `{ game_code: "complete" }`. */
  is_file?: Record<string, unknown> | null
  site_js?: Record<string, unknown> | null
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
  /** Completion fields copied from a site / JS / is-file probe. */
  scrape?: Record<string, unknown>
}

/** Listing signal. Same fields as `listing_scan_latest.json` `new_listing_signals[]`. */
export interface ListingSignal {
  name?: string
  handle?: string
  signal: string
  prev?: string | null
  keyword?: string
  source?: string
  /** Completion fields copied from the signal object, separate from free-text `signal`. */
  scrape?: Record<string, unknown>
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

/** Where a contract address was spotted. Canonical values match `ca_finds.json`. */
export type CaFindSource = 'site' | 'js' | 'x' | 'tg' | 'on-chain'

export type CaFindConfidence = 'high' | 'medium' | 'low'

/** Schema v2 status. Name-only matches stay `suspected_copycat`, not a confirmed CA. */
export type CaStatus = 'confirmed' | 'candidate' | 'superseded' | 'not_ca' | 'suspected_copycat' | ''

/** Why a row was confirmed. Empty when the pipeline has not established provenance. */
export type CaProvenance = 'wallet_factory' | 'official_x' | 'both' | ''

export type CaRole = 'token' | 'transistors' | 'processor' | ''

/**
 * One address row from `ca_finds.json` (`finds`, `suspected_copycats`, `wallet_activity`, or archived superseded history).
 * `alertOk` is the only signal that may sound or highlight a new CA. `caLocked` stops later CA alerts upstream;
 * wallet activity for that project is still a row and is not a CA alert.
 */
export interface CaFind {
  project: string
  handle: string
  chain: string
  address: string
  source: string
  /** Raw discovery strings from `source` and `sources[]`, primary first. */
  sourceRefs: string[]
  evidence_url: string
  detected_at: string
  confidence: CaFindConfidence | ''
  note: string
  labelZh: string
  caStatus: CaStatus
  caStatusZh: string
  provenance: CaProvenance
  provenanceZh: string
  officialXConfirmed: boolean
  walletFactoryConfirmed: boolean
  officialXUrl: string
  caRole: CaRole
  alertOk: boolean
  supersededBy: string
  pairedWith: string
  confirmBasisZh: string
  creator: string
  /** null when the pipeline did not say whether the creator is a watched wallet. */
  creatorWatched: boolean | null
  tx: string
  cpu: string
  mintPriceBnb: string
  supplyCap: string
  processor: string
  transistors: string
  caLocked: boolean
  lockUrl: string
  /** Pipeline key such as `taperobot_bsc`, also listed in `ca_locked_projects`. */
  projectKey: string
  lockAt: string
  /** Watched-wallet activity. Shown even after an official-X lock. Never a CA alert. */
  activity: boolean
  /** From `launched_history`. Not part of the active status_counts. Shown under 已开盘. */
  archived: boolean
}

export interface CaStatusCounts {
  confirmed: number
  candidate: number
  superseded: number
  not_ca: number
}

/** A project whose official X has posted a verified CA. */
export interface CaProjectLock {
  id: string
  project: string
  handle: string
  url: string
  aliases: string[]
}

export interface CaFindsPayload {
  generated_at?: string
  schemaVersion?: number
  confidenceModel?: string
  statusCounts: CaStatusCounts
  confirmedCount: number
  candidateCount: number
  suspectedCopycatCount: number
  finds: CaFind[]
  suspectedCopycats: CaFind[]
  /** Superseded rows from the active list and from `launched_history`. */
  supersededArchive: CaFind[]
  /** Every `launched_history` row, including confirmed and candidate. */
  launchedHistory: CaFind[]
  walletActivity: CaFind[]
  locks: CaProjectLock[]
}
