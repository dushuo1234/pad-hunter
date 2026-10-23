/**
 * Turn machine-written English CA notes into Chinese for display.
 * Addresses, token symbols, and standards such as ERC20 stay as written.
 * Chinese text that does not match a machine phrase is left unchanged.
 */

type Replacer = (match: string, ...groups: string[]) => string

const PHRASES: Array<[RegExp, string | Replacer]> = [
  [
    // On-chain symbols are free text and may contain spaces. Stop at dec=.
    /(?:ca_gate:\s*)?ERC20 verified:\s*(.+?)\s*dec=(\d+)/gi,
    (_match, symbol, decimals) => `核验：已确认 ERC20（符号 ${symbol.trim()}，精度 ${decimals}）`,
  ],
  [
    /(?:ca_gate:\s*)?NFT contract \(([^)]+)\)\s*[—–-]+\s*not a token CA/gi,
    (_match, standard) => `核验：NFT 合约（${standard}），不是代币 CA`,
  ],
  [
    /(?:ca_gate:\s*)?SPL mint verified \(([^)]*)\)/gi,
    (_match, inner) => `核验：已确认 SPL mint（${translateSplInner(inner)}）`,
  ],
  [
    /(?:ca_gate:\s*)?eth_getCode empty\s*\/\s*7702\s*(?:→|->)\s*EOA wallet/gi,
    '核验：eth_getCode 为空或为 7702，判定为 EOA 钱包',
  ],
  [/(?:ca_gate:\s*)?not a valid Solana pubkey/gi, '核验：不是有效的 Solana 公钥'],
  [
    /(?:ca_gate:\s*)?hex string \(hash\s*\/\s*git SHA\),?\s*not a Solana address/gi,
    '核验：是十六进制字符串（哈希 / git SHA），不是 Solana 地址',
  ],
  [
    /(?:ca_gate:\s*)?contract bytecode but no ERC20 decimals\/symbol\s*[—–-]+\s*not a token CA/gi,
    '核验：有合约字节码，但没有 ERC20 精度或符号，不是代币 CA',
  ],
  [/(?:ca_gate:\s*)?account does not exist on Solana mainnet/gi, '核验：Solana 主网上不存在该账户'],
  [
    /low confidence:\s*feed-style site that embeds third-party token icons\/posts/gi,
    '低置信：信息流站点嵌入第三方代币图标/帖子',
  ],
  [/medium confidence:\s*/gi, '中置信：'],
  [/high confidence:\s*/gi, '高置信：'],
  [/low confidence:\s*/gi, '低置信：'],
  [/likely not this project's own CA/gi, '多半不是本项目自有 CA'],
  [
    /taken from a token-icon URL on the page \(may be a third-party token\)/gi,
    '来自页面代币图标 URL（可能是第三方）',
  ],
  [/classified as EOA\/wallet via eth_getCode/gi, '经 eth_getCode 判定为 EOA 钱包'],
  [/classified as contract \((\d+) bytes\)/gi, (_match, bytes) => `判定为合约（${bytes} 字节）`],
  [
    /appears as a \?ref= referral parameter\s*[—–-]+\s*likely a wallet, not a token CA/gi,
    '出现在 ?ref= 推荐参数中，多半是钱包而不是代币 CA',
  ],
  [/address appears all-lowercase \(taken from a URL\)/gi, '地址全为小写（取自 URL）'],
  [/Solana is case-sensitive\s*[—–-]+\s*verify exact mint/gi, 'Solana 地址区分大小写，需核对准确的 mint'],
  [/name_match_unconfirmed/gi, '同名未确认'],
  [/never confirmed/gi, '从未被确认'],
  [
    /onchain_lock\s+(low|medium|high|confirmed)\s+via\s+([^;；]+)/gi,
    (_match, level, via) => `链上锁定：${lockLevel(level)}，依据${viaZh(via.trim())}`,
  ],
  [
    /watched wallet\s+(\S+)\s+created\s+(\S+)\s+but\s+(@?\S+)\s+named\s+(\S+)/gi,
    (_match, wallet, at, account, named) => `监控钱包 ${wallet} 于 ${at} 创建，但 ${account} 指定的是 ${named}`,
  ],
  [/deployer=(0x[a-fA-F0-9]+)/g, (_match, address) => `部署者 ${address}`],
  [/creator=(0x[a-fA-F0-9]+)/g, (_match, address) => `创建者 ${address}`],
  [/tx=(0x[a-fA-F0-9]+)/g, (_match, hash) => `交易 ${hash}`],
  [/deployer=(?:none|null)/gi, ''],
  [/creator=(?:none|null)/gi, ''],
  [/tx=(?:none|null)/gi, ''],
  [/superseded_by=(0x[a-fA-F0-9]+)/gi, (_match, address) => `已被取代，现用 ${address}`],
  [/token=([^;；]+)/gi, (_match, token) => `代币 ${token.trim()}`],
  [/via\s+x:(@?\S+)/gi, (_match, handle) => `来源官推 ${handle.startsWith('@') ? handle : `@${handle}`}`],
  [
    /via\s+factory:([^:;\s]+):creator_watched/gi,
    (_match, factory) => `来源工厂 ${factory}（创建者在监控钱包）`,
  ],
  [/(^|[^\u4e00-\u9fff])Processor\b/g, (_match, prefix) => `${prefix}处理器`],
  [/ca_gate:\s*/gi, '核验：'],
]

function lockLevel(level: string): string {
  const key = level.toLowerCase()
  if (key === 'low') return '低置信'
  if (key === 'medium') return '中置信'
  if (key === 'high') return '高置信'
  if (key === 'confirmed') return '已确认'
  return level
}

function viaZh(raw: string): string {
  const walletToken = raw.match(/^wallet\+token:symbol:(.+)$/i)
  if (walletToken) return `监控钱包+代币符号 ${walletToken[1].trim()}`
  const symbolAndName = raw.match(/^symbol:(.+?)\+name:(.+)$/i)
  if (symbolAndName) return `符号 ${symbolAndName[1].trim()} 且名称 ${symbolAndName[2].trim()}`
  const fuzzy = raw.match(/^name_fuzzy:(.+)$/i)
  if (fuzzy) return `名称模糊匹配 ${fuzzy[1].trim()}`
  const symbol = raw.match(/^symbol:(.+)$/i)
  if (symbol) return `符号 ${symbol[1].trim()}`
  const name = raw.match(/^name:(.+)$/i)
  if (name) return `名称 ${name[1].trim()}`
  return raw
}

function translateSplInner(inner: string): string {
  return inner
    .replace(/owner\s+/i, '拥有者 ')
    .replace(/dec=(\d+)/i, '精度 $1')
    .replace(/,\s*/g, '，')
}

function applyPhrases(text: string): string {
  let next = text
  for (const [pattern, replacement] of PHRASES) {
    next = typeof replacement === 'string' ? next.replace(pattern, replacement) : next.replace(pattern, replacement)
  }
  return next
}

function translateClause(clause: string): string {
  const trimmed = clause.trim()
  if (!trimmed || /^(?:creator|tx)=?$/.test(trimmed)) return ''
  const bracket = trimmed.match(/^(【[^】]*】)\s*(.*)$/)
  const prefix = bracket ? applyPhrases(bracket[1]) : ''
  const body = applyPhrases((bracket ? bracket[2] : trimmed).trim())
  if (!body || /^(?:creator|tx)=?$/.test(body)) return prefix
  if (!prefix) return body
  return `${prefix}${/^[\s，；。]/.test(body) ? '' : ' '}${body}`
}

/** Localize one note, label, or confirm-basis string. Safe to call on text that is already Chinese. */
export function localizeMachineNote(input: string | null | undefined): string {
  const text = input?.trim() ?? ''
  if (!text) return ''
  const parts = text
    .split(/\s*[;；]\s*/)
    .map((part) => translateClause(part))
    .filter(Boolean)
  return parts.join('；')
}
