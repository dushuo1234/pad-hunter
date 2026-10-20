import type { Candidate, Filters } from '../types'
import { categoryOf } from './categories'
import { followerCount, sourceChannel } from './format'

export const SOURCE_ORDER = ['telegram:项目推送监控', 'telegram:项目推送']

export function candidateSource(candidate: Candidate, payloadSource?: string): string {
  const own = candidate.source?.trim()
  if (own) return own
  const fallback = payloadSource?.trim()
  if (fallback && !fallback.includes('+') && !fallback.includes(',')) return fallback
  return ''
}

export function withSourceFallback(candidates: Candidate[], payloadSource?: string): Candidate[] {
  return candidates.map((candidate) => {
    const source = candidateSource(candidate, payloadSource)
    if (!source || candidate.source === source) return candidate
    return { ...candidate, source }
  })
}

export function sortSources(names: Iterable<string>): string[] {
  return [...new Set(names)].sort((a, b) => {
    const ia = SOURCE_ORDER.indexOf(a)
    const ib = SOURCE_ORDER.indexOf(b)
    if (ia === -1 && ib === -1) return a.localeCompare(b, 'zh')
    if (ia === -1) return 1
    if (ib === -1) return -1
    return ia - ib
  })
}

export function findByHandle(candidates: Candidate[], handle: string): Candidate | undefined {
  const key = handle.replace(/^@/, '').trim().toLowerCase()
  if (!key) return undefined
  const matches = candidates.filter((candidate) => candidate.handle.replace(/^@/, '').toLowerCase() === key)
  matches.sort((a, b) => (Date.parse(b.date_iso || '') || 0) - (Date.parse(a.date_iso || '') || 0))
  return matches[0]
}

export function matches(candidate: Candidate, filters: Filters, ignoreCategory: boolean): boolean {
  if (filters.chain && candidate.chain !== filters.chain) return false
  if (filters.source && candidateSource(candidate) !== filters.source) return false
  if (followerCount(candidate.followers) < filters.minFollowers) return false
  if ((candidate.kol_followers || 0) < filters.minKol) return false
  if (!ignoreCategory && filters.category && categoryOf(candidate) !== filters.category) return false
  const q = filters.search.trim().toLowerCase()
  if (q) {
    const hay =
      `${candidate.name} ${candidate.handle} ${candidate.why} ${candidate.bio} ${candidate.notes ?? ''} ${candidate.chain} ${categoryOf(candidate)} ${candidate.status ?? ''} ${candidate.listing ?? ''} ${candidate.risk ?? ''} ${sourceChannel(candidate.source)} ${candidate.source ?? ''}`.toLowerCase()
    if (!hay.includes(q)) return false
  }
  return true
}

export function compareCandidates(sort: Filters['sort']) {
  return (a: Candidate, b: Candidate) => {
    if (sort === 'followers') return followerCount(b.followers) - followerCount(a.followers)
    if (sort === 'kol_followers') return (b.kol_followers || 0) - (a.kol_followers || 0)
    if (sort === 'score') return (b.score || 0) - (a.score || 0) || a.rank - b.rank
    const ta = Date.parse(a.date_iso || '') || 0
    const tb = Date.parse(b.date_iso || '') || 0
    if (tb !== ta) return tb - ta
    return a.rank - b.rank
  }
}
