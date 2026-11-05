import type { Candidate } from '../types'
import type { MonitorSnapshot } from './monitor'

/** Phrases that mean the project is already open / listed / trading. */
const OPENED_CN = ['已开盘', '已上线', '已上市', '开盘中', '交易中', '正在交易'] as const

/** A mint that is running now means the sale has opened. The lookahead keeps 「mint中午」 (a time, not a state) from matching. */
const MINT_LIVE_RE = /mint\s*进行中|mint中(?![午晚])|正在\s*mint/i

function mintIsLive(value: string): boolean {
  return MINT_LIVE_RE.test(value)
}

const FIELD_PATTERN = /(?:^|[;\n；])\s*(listing|status)\s*[=：]\s*([^;\n；]+)/gi

function fieldSaysOpened(value: string | null | undefined): boolean {
  const text = value?.trim() ?? ''
  if (!text) return false
  if (OPENED_CN.some((phrase) => text.includes(phrase))) return true
  if (mintIsLive(text)) return true
  if (/^(live|trading|listed)$/i.test(text)) return true
  if (/\b(?:now|already|currently)\s+listed\b/i.test(text)) return true
  return englishSaysOpened(text)
}

/** Short status fields match `live` / `trading`. Longer blurbs only match a clear "already live" phrase. */
function englishSaysOpened(text: string): boolean {
  const live = /\blive\b/i.test(text)
  const trading = /\btrading\b/i.test(text)
  if (!live && !trading) return false
  const pendingLive =
    /\b(?:not|pre|before|going|upcoming)\b[\s-]*live\b/i.test(text) ||
    /\blive\s+soon\b/i.test(text) ||
    /\bwill\s+be\s+live\b/i.test(text) ||
    /\byet\s+to\s+(?:go\s+)?live\b/i.test(text)
  const definitelyLive = /\b(?:now|already|currently|went)\s+live\b/i.test(text)
  const liveOpened = live && (!pendingLive || definitelyLive)
  const tradingOpened = trading && !/\b(?:not|pre|before)\b[\s-]*trading\b/i.test(text)
  if (text.length > 48 && !definitelyLive && !/\b(?:now|started|already)\s+trading\b/i.test(text)) {
    return false
  }
  return liveOpened || tradingOpened
}

function signalSaysOpened(text: string | null | undefined): boolean {
  const raw = text?.trim() ?? ''
  if (!raw) return false
  const fields: string[] = []
  for (const match of raw.matchAll(new RegExp(FIELD_PATTERN.source, 'gi'))) {
    const value = match[2]?.trim()
    if (value) fields.push(value)
  }
  if (fields.length > 0) return fields.some((field) => fieldSaysOpened(field))
  return fieldSaysOpened(raw)
}

/** True when the candidate or the latest monitor listing says the project is already open. */
export function isAlreadyOpened(candidate: Candidate, snap: MonitorSnapshot): boolean {
  if (fieldSaysOpened(candidate.listing) || fieldSaysOpened(candidate.status)) return true
  if (signalSaysOpened(snap.lastSignal?.text) || signalSaysOpened(candidate.listing_signal)) return true
  // The X-progress scanner's 疑似已开盘 verdict lives in its own fields; without
  // reading them, a flagged project stays on upcoming lists until a human marks it.
  if (candidate.x_progress_bucket === 'already_live') return true
  if (fieldSaysOpened(candidate.x_progress_signal)) return true
  return false
}
