export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K`
  return String(n)
}

/** Accept a number or a Telegram fans string (`粉丝 1.2万 · 你圈子 1 人`). */
export function followerCount(value: number | string | null | undefined): number {
  if (typeof value === 'number' && Number.isFinite(value)) return Math.max(0, Math.trunc(value))
  if (typeof value !== 'string') return 0
  const match = value.replace(/,/g, '').match(/(\d+(?:\.\d+)?)\s*([kKmM万])?/)
  if (!match) return 0
  let n = Number(match[1])
  if (!Number.isFinite(n)) return 0
  const unit = match[2] || ''
  if (unit.toLowerCase() === 'k') n *= 1_000
  else if (unit.toLowerCase() === 'm') n *= 1_000_000
  else if (unit === '万') n *= 10_000
  return Math.trunc(n)
}

export function xProfileUrl(handle: string): string {
  return `https://x.com/${handle.replace(/^@/, '')}`
}

export function sameXUrl(a: string, b: string): boolean {
  const norm = (url: string) =>
    url
      .trim()
      .replace(/\/+$/, '')
      .toLowerCase()
      .replace('://twitter.com', '://x.com')
      .replace('://mobile.twitter.com', '://x.com')
      .replace('://mobile.x.com', '://x.com')
  return norm(a) === norm(b)
}

export function formatShanghai(iso?: string, withSeconds = false): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  const options: Intl.DateTimeFormatOptions = {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }
  if (withSeconds) options.second = '2-digit'
  return date.toLocaleString('zh-CN', options)
}

export function formatLatency(timeS?: number): string {
  if (timeS == null || Number.isNaN(timeS)) return ''
  if (timeS < 10) return `${Math.round(timeS * 1000)}ms`
  return `${timeS.toFixed(1)}s`
}

export function shortAddr(value?: string | null): string {
  if (!value) return ''
  if (value.length <= 18) return value
  return `${value.slice(0, 8)}…${value.slice(-4)}`
}

export function sourceChannel(source?: string): string {
  if (!source) return ''
  const trimmed = source.trim()
  if (trimmed.startsWith('telegram:')) return trimmed.slice('telegram:'.length)
  return trimmed
}

export function decodeSnippet(text: string): string {
  return text
    .replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
}
