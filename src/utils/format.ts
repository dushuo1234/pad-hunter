export function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, '')}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, '')}K`
  return String(n)
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

export function formatShanghai(iso?: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
}
