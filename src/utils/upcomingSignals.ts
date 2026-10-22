import type { Candidate } from '../types'

/**
 * High completion threshold.
 * A 0–1 fraction qualifies at 0.8. A 1–100 score qualifies at 80.
 * Labels such as high / complete / 完成 / 就绪 also qualify. low and medium do not.
 */
export const HIGH_COMPLETION = 0.8

export interface CompletionFacets {
  project: boolean
  contract: boolean
  game: boolean
}

const PROJECT_KEYS = new Set([
  'readiness',
  'completion',
  'project_completion',
  'site_completion',
  'js_completion',
  'site_js_completion',
  'js_readiness',
  'is_completion',
  'is_file_completion',
  'isfile_completion',
  'project_readiness',
  'site_readiness',
  'overall_completion',
  'completeness',
  '完成度',
  '项目完成度',
  '站点完成度',
])

const CONTRACT_KEYS = new Set([
  'contract_completion',
  'contract_code_completion',
  'contract_readiness',
  'contract_code',
  'contracts_completion',
  'contract_code_readiness',
  '合约完成度',
  '合约代码',
  '合约代码完成度',
])

const GAME_KEYS = new Set([
  'game_completion',
  'game_code_completion',
  'game_readiness',
  'game_code',
  'gameplay_completion',
  'game_code_readiness',
  '游戏完成度',
  '游戏代码',
  '游戏代码完成度',
])

/** Containers the site / JS / is-file scraper may nest completion under. */
const NEST_KEYS = new Set([
  'site_js',
  'js',
  'js_scan',
  'is',
  'is_file',
  'isfile',
  'scrape',
  'site_scrape',
])

/** A bare true / high on these means the is-file or JS scrape says the project is ready. */
const PROJECT_NESTS = new Set(['is', 'is_file', 'isfile', 'site_js', 'js', 'js_scan'])

const VALUE_KEYS = new Set([
  'completion',
  'readiness',
  'percent',
  'percentage',
  'score',
  'level',
  'status',
  'value',
  'label',
  '完成度',
])

const HIGH_LABELS = new Set([
  'high',
  'very high',
  'ready',
  'complete',
  'completed',
  'done',
  'full',
  'sufficient',
  '高',
  '很高',
  '高完成度',
  '完成',
  '已完成',
  '完备',
  '齐全',
  '就绪',
  '已就绪',
])

const LOW_LABELS = new Set([
  'low',
  'medium',
  'mid',
  'partial',
  'incomplete',
  'unknown',
  '未知',
  '低',
  '中',
  '未完成',
  '开发中',
  '无',
  'false',
  'no',
  'none',
  'pending',
])

const STARTING_CN = ['即将启动', '即将上线', '即将发布', '即将开盘', '即将开始']
const STARTING_EN = [
  /about to (?:start|launch)/i,
  /start(?:ing)? soon/i,
  /launch(?:ing)? soon/i,
  /coming soon/i,
  /launch imminent/i,
]

type Facet = keyof CompletionFacets

function normalizeKey(key: string): string {
  const text = key.trim()
  if (/[\u3400-\u9fff]/.test(text)) return text
  return text.toLowerCase().replace(/[\s-]+/g, '_')
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function facetOf(key: string): Facet | null {
  if (PROJECT_KEYS.has(key)) return 'project'
  if (CONTRACT_KEYS.has(key)) return 'contract'
  if (GAME_KEYS.has(key)) return 'game'
  return null
}

function isScrapeKey(key: string): boolean {
  return facetOf(key) != null || NEST_KEYS.has(key)
}

export function isHighCompletion(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number' && Number.isFinite(value)) {
    if (value >= 0 && value <= 1) return value >= HIGH_COMPLETION
    if (value > 1 && value <= 100) return value >= HIGH_COMPLETION * 100
    return false
  }
  if (typeof value !== 'string') return false
  const text = value.trim().toLowerCase()
  if (!text || text.length > 48) return false
  if (LOW_LABELS.has(text)) return false
  if (HIGH_LABELS.has(text)) return true
  const percent = text.match(/^(\d+(?:\.\d+)?)\s*%$/)
  if (percent) return isHighCompletion(Number(percent[1]))
  if (/^\d+(?:\.\d+)?$/.test(text)) return isHighCompletion(Number(text))
  return false
}

/** Copy completion / is-file fields off a candidate, site probe, or listing signal. */
export function pickScrape(row: Record<string, unknown> | null | undefined): Record<string, unknown> | undefined {
  if (!row) return undefined
  const out: Record<string, unknown> = {}
  for (const key of Object.keys(row)) {
    const normalized = normalizeKey(key)
    if (!isScrapeKey(normalized)) continue
    const value = row[key]
    if (value == null || value === '') continue
    out[normalized] = value
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function mergeScrape(
  ...parts: Array<Record<string, unknown> | undefined>
): Record<string, unknown> | undefined {
  const out: Record<string, unknown> = {}
  for (const part of parts) {
    if (!part) continue
    Object.assign(out, part)
  }
  return Object.keys(out).length > 0 ? out : undefined
}

function absorb(value: unknown, facet: Facet, facets: CompletionFacets, depth: number) {
  if (isHighCompletion(value)) {
    facets[facet] = true
    return
  }
  if (!isRecord(value) || depth > 4) return
  for (const [rawKey, child] of Object.entries(value)) {
    const key = normalizeKey(rawKey)
    const childFacet = facetOf(key)
    if (childFacet) {
      absorb(child, childFacet, facets, depth + 1)
      continue
    }
    if (NEST_KEYS.has(key)) {
      if (PROJECT_NESTS.has(key) && isHighCompletion(child)) facets.project = true
      if (isRecord(child)) walkRecord(child, facets, depth + 1)
      continue
    }
    if (VALUE_KEYS.has(key) && isHighCompletion(child)) facets[facet] = true
  }
}

function walkRecord(record: Record<string, unknown>, facets: CompletionFacets, depth: number) {
  if (depth > 4) return
  for (const [rawKey, value] of Object.entries(record)) {
    const key = normalizeKey(rawKey)
    const facet = facetOf(key)
    if (facet) {
      absorb(value, facet, facets, depth)
      continue
    }
    if (!NEST_KEYS.has(key)) continue
    if (PROJECT_NESTS.has(key) && isHighCompletion(value)) facets.project = true
    if (isRecord(value)) walkRecord(value, facets, depth + 1)
  }
}

const SIGNAL_FIELD = /(?:^|[;\n；])\s*([^=：;\n；]{1,40}?)\s*[=：]\s*([^;\n；]+)/g

export function recordFromSignalText(text: string | null | undefined): Record<string, unknown> | undefined {
  const raw = text?.trim() ?? ''
  if (!raw) return undefined
  const out: Record<string, unknown> = {}
  for (const match of raw.matchAll(new RegExp(SIGNAL_FIELD.source, 'g'))) {
    const key = normalizeKey(match[1] ?? '')
    const value = match[2]?.trim() ?? ''
    if (!key || !value || !isScrapeKey(key)) continue
    out[key] = value
  }
  return Object.keys(out).length > 0 ? out : undefined
}

export function completionFacets(records: Array<Record<string, unknown> | undefined>): CompletionFacets {
  const facets: CompletionFacets = { project: false, contract: false, game: false }
  for (const record of records) {
    if (record) walkRecord(record, facets, 0)
  }
  return facets
}

export function completionTags(facets: CompletionFacets): string[] {
  const tags: string[] = []
  if (facets.project) tags.push('站点/JS 完成度高')
  if (facets.contract) tags.push('合约代码完成度高')
  if (facets.game) tags.push('游戏代码完成度高')
  return tags
}

function isNegated(text: string): boolean {
  return /非即将|不是即将|not\s+(?:about|starting|launching|coming)/i.test(text)
}

function fieldSaysStarting(value: string | null | undefined): boolean {
  const text = value?.trim() ?? ''
  if (!text || text.length > 80 || isNegated(text)) return false
  if (STARTING_CN.some((phrase) => text.includes(phrase))) return true
  return STARTING_EN.some((pattern) => pattern.test(text))
}

function signalSaysStarting(text: string | null | undefined): boolean {
  const raw = text?.trim() ?? ''
  if (!raw) return false
  const fields: string[] = []
  for (const match of raw.matchAll(/(?:^|[;\n；])\s*(listing|status)\s*[=：]\s*([^;\n；]+)/gi)) {
    const value = match[2]?.trim()
    if (value) fields.push(value)
  }
  if (fields.length > 0) return fields.some((field) => fieldSaysStarting(field))
  return fieldSaysStarting(raw)
}

export function isAboutToStart(
  candidate: Pick<Candidate, 'status' | 'listing' | 'listing_signal'>,
  signalText?: string | null,
): boolean {
  if (fieldSaysStarting(candidate.status) || fieldSaysStarting(candidate.listing)) return true
  if (signalSaysStarting(signalText) || signalSaysStarting(candidate.listing_signal)) return true
  return false
}
