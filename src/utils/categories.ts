import type { Candidate } from '../types'

/** Preferred column / chip order for 「项目推送」 categories. */
export const CATEGORY_ORDER = [
  '发射台',
  'Meme币',
  'GameFi',
  'NFT铸造',
  'DeFi协议',
  'AI代理',
  '基础设施',
  '其他',
]

const CHAIN_LAST = new Set(['未知', '其他', '其他/未知', '未分类'])

export function categoryOf(candidate: Pick<Candidate, 'category'>): string {
  const value = candidate.category?.trim()
  return value || '未分类'
}

export function sortCategories(names: Iterable<string>): string[] {
  return [...names].sort((a, b) => {
    const ia = CATEGORY_ORDER.indexOf(a)
    const ib = CATEGORY_ORDER.indexOf(b)
    if (ia === -1 && ib === -1) return a.localeCompare(b, 'zh')
    if (ia === -1) return 1
    if (ib === -1) return -1
    return ia - ib
  })
}

export function sortChains(names: Iterable<string>): string[] {
  return [...names].sort((a, b) => {
    const aLast = CHAIN_LAST.has(a)
    const bLast = CHAIN_LAST.has(b)
    if (aLast !== bLast) return aLast ? 1 : -1
    return a.localeCompare(b, 'zh')
  })
}
