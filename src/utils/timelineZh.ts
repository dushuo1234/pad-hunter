import { localizeMachineNote } from './caNoteZh'
import { caSourceLabel } from './caFinds'

const SOURCE_NAMES: Record<string, string> = {
  listing_times: '开盘时间表',
  listing_scan: '开盘扫描',
  watchlist: '监控名单',
  ca_finds: '发现CA',
  latest: '站点快照',
  x_bio: '官推简介',
  x_post: '官推',
  x: '官推X',
  twitter: '官推X',
  tg: 'Telegram',
  telegram: 'Telegram',
  site: '官网',
  js: '官网JS',
  onchain: '链上',
  'on-chain': '链上',
  sample: '示例',
}

const KEY_LABELS: Record<string, string> = {
  status: '状态',
  listing: '开盘',
  keyword: '关键词',
  source: '来源',
  prev: '先前',
  confidence: '置信',
  ca_status: 'CA状态',
  ca_gate: '核验',
  alert_ok: '允许提醒',
  note: '备注',
  chain: '链',
  http_code: 'HTTP',
  site_change: '站点变更',
}

const TOKEN_LABELS: Array<[RegExp, string]> = [
  [/\bSITE_CHANGE\b/g, '站点变更'],
  [/\balert_ok\b/gi, '允许提醒'],
  [/\blow-confidence\b/gi, '低置信'],
  [/\bmedium-confidence\b/gi, '中置信'],
  [/\bhigh-confidence\b/gi, '高置信'],
  [/\blisting_times\b/g, '开盘时间表'],
  [/\blisting_scan\b/g, '开盘扫描'],
  [/\bca_finds\b/g, '发现CA'],
  [/\bwatchlist\b/g, '监控名单'],
  [/\bx_post\b/g, '官推'],
  [/\bx_bio\b/g, '官推简介'],
  [/\blatest\b/g, '站点快照'],
  [/\bsample\b/gi, '示例'],
  [/\bhandle\b/gi, '账号'],
]

/** Status badge on a site probe. `up` / `down` never stay in English. */
export function timelineHealthLabel(health: 'up' | 'down' | 'unknown', raw?: string | null): string {
  if (health === 'up') return '可用'
  if (health === 'down') return '不可用'
  const text = (raw ?? '').trim().toLowerCase()
  if (!text || text === 'checked' || text === 'unknown' || text === 'probe') return '已探测'
  return localizeTimelineText(raw) || '已探测'
}

export function timelineLatency(timeS?: number | null): string {
  if (timeS == null || Number.isNaN(timeS)) return ''
  if (timeS < 10) return `${Math.round(timeS * 1000)} 毫秒`
  return `${timeS.toFixed(1)} 秒`
}

/** Discovery source, file name, or `site:https://…` string shown on a timeline row. */
export function timelineSourceLabel(source: string | null | undefined): string {
  const text = source?.trim() ?? ''
  if (!text) return ''
  const named = SOURCE_NAMES[text.toLowerCase()]
  if (named) return named
  const labeled = caSourceLabel(text)
  if (labeled && labeled !== '其他来源') return labeled
  return localizeTimelineText(text)
}

/** Known machine phrases, `key=value` fields, and CA notes. Free-form names stay as written. */
export function localizeTimelineText(input: string | null | undefined): string {
  const text = input?.trim() ?? ''
  if (!text) return ''
  const keyed = text
    .split(/\s*[;；]\s*/)
    .map((part) => localizeClause(part))
    .filter(Boolean)
  return keyed.join('；')
}

export function localizeProbeError(input: string | null | undefined): string {
  const text = input?.trim() ?? ''
  if (!text) return ''
  if (/could not resolve host|enotfound|name or service not known/i.test(text)) return '无法解析域名'
  if (/timed out|timeout|etimedout/i.test(text)) return '连接超时'
  if (/ssl|certificate|cert/i.test(text)) return '证书校验失败'
  if (/connection refused|econnrefused/i.test(text)) return '连接被拒绝'
  const http = text.match(/\bhttp\s*(\d{3})\b/i)
  if (http) {
    const code = http[1]
    if (code === '404') return 'HTTP 404 未找到'
    if (code === '502') return 'HTTP 502 网关错误'
    if (code === '503') return 'HTTP 503 服务不可用'
    if (code === '500') return 'HTTP 500 服务器错误'
    return `HTTP ${code}`
  }
  return localizeTimelineText(text)
}

/** Footer under the timeline. File names and pipeline ids become Chinese. */
export function localizeEventsNote(input: string | null | undefined): string {
  const text = input?.trim() ?? ''
  if (!text) return ''
  return localizeTimelineText(text)
    .replace(/\bhandle\b/gi, '账号')
    .replace(/public\/data\/monitor_events\.json/gi, '监控事件数据')
    .replace(/\bmonitor_events\.json\b/gi, '监控事件数据')
}

function localizeClause(clause: string): string {
  const trimmed = clause.trim()
  if (!trimmed) return ''
  const machine = localizeMachineNote(trimmed)
  if (machine && machine !== trimmed) return machine
  const field = trimmed.match(/^([A-Za-z][A-Za-z0-9_]*)\s*[:=]\s*(.*)$/)
  if (field) {
    const label = KEY_LABELS[field[1].toLowerCase()]
    const value = localizeValue(field[2])
    if (label) return value ? `${label} ${value}` : label
  }
  return localizeValue(trimmed)
}

function localizeValue(value: string): string {
  let next = value.trim()
  if (!next) return ''
  for (const [pattern, replacement] of TOKEN_LABELS) next = next.replace(pattern, replacement)
  next = localizeMachineNote(next)
  const whole = SOURCE_NAMES[next.toLowerCase()]
  return whole ?? next
}
