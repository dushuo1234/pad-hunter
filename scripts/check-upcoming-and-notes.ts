import { readFileSync } from 'node:fs'
import { localizeMachineNote } from '../src/utils/caNoteZh.ts'
import { upcomingLaunches } from '../src/utils/launch.ts'
import { collectMonitorEvents } from '../src/utils/monitor.ts'
import type { Candidate, MonitorEvent } from '../src/types/index.ts'

function fail(message: string): never {
  throw new Error(message)
}

function candidate(partial: Partial<Candidate> & Pick<Candidate, 'handle' | 'name'>): Candidate {
  return {
    rank: 1,
    followers: 0,
    kol_followers: 0,
    bio: '',
    why: '',
    score: 0,
    tweet_url: '',
    chain: 'ETH',
    ...partial,
  }
}

const now = new Date('2026-10-22T08:00:00+08:00')

const timedSoon = candidate({
  handle: 'soon',
  name: 'Soon',
  listing_at: '2026-10-23T12:00:00+08:00',
  status: '开发中',
  listing: '未开盘',
})
const timedLater = candidate({
  handle: 'later',
  name: 'Later',
  listing_at: '2026-10-24T09:00:00+08:00',
  status: '开发中',
  listing: '未开盘',
})
const outside = candidate({
  handle: 'outside',
  name: 'Outside',
  listing_at: '2026-11-09T00:00:00+08:00',
  status: '即将启动',
  listing: '未开盘',
})
const starting = candidate({
  handle: 'hydra',
  name: 'Agent HYDRA',
  status: '即将启动',
  listing: '未开盘',
  listing_at: null,
  date_iso: '2026-10-21T12:00:00Z',
  why: '时间未知也不该编造',
})
const olderStarting = candidate({
  handle: 'older',
  name: 'Older Start',
  status: 'about to launch',
  listing: '未开盘',
  date_iso: '2026-10-01T00:00:00Z',
})
const signalStarting = candidate({
  handle: 'sig',
  name: 'Signal',
  status: '开发中',
  listing: '未开盘',
  listing_signal: 'status=即将启动; listing=未开盘',
  date_iso: '2026-10-20T00:00:00Z',
})
const prose = candidate({
  handle: 'prose',
  name: 'Prose',
  status: '开发中',
  listing: '未开盘',
  why: '文案里写了即将启动，但状态不是',
  bio: 'high completion in a sentence should not count',
})
const opened = candidate({
  handle: 'opened',
  name: 'Opened',
  status: '已开盘',
  listing: '未开盘',
})
const listed = candidate({
  handle: 'listed',
  name: 'Listed',
  status: '即将启动',
  listing: '未开盘',
  already_listed: true,
})
const contractReady = candidate({
  handle: 'code',
  name: 'Contract Ready',
  status: '开发中',
  listing: '未开盘',
  contract_code_completion: 0.91,
  date_iso: '2026-10-18T00:00:00Z',
})
const gameLow = candidate({
  handle: 'gamelow',
  name: 'Game Low',
  status: '开发中',
  listing: '未开盘',
  game_code: 'low',
})
const gameNested = candidate({
  handle: 'gamenest',
  name: 'Game Nest',
  status: '不明',
  listing: '未开盘',
  is_file: { game_code: 'complete' },
  date_iso: '2026-10-19T00:00:00Z',
})
const longCode = candidate({
  handle: 'snippet',
  name: 'Snippet',
  status: '开发中',
  listing: '未开盘',
  contract_code: 'function transfer() { return "this is source, not a completion score, and it is long"; }',
})

const events: MonitorEvent[] = [
  {
    id: 'site|jsready',
    kind: 'site',
    at: '2026-10-21T00:00:00Z',
    handle: 'jsready',
    name: 'JS Ready',
    site: {
      url: 'https://example.test/',
      status: 'up',
      scrape: { js_completion: '85%' },
    },
  },
]

const jsReady = candidate({
  handle: 'jsready',
  name: 'JS Ready',
  status: '开发中',
  listing: '未开盘',
  date_iso: '2026-10-17T00:00:00Z',
})

const rows = upcomingLaunches(
  [
    prose,
    opened,
    listed,
    outside,
    gameLow,
    longCode,
    olderStarting,
    gameNested,
    contractReady,
    signalStarting,
    starting,
    jsReady,
    timedLater,
    timedSoon,
  ],
  events,
  [],
  now,
)

const handles = rows.map((row) => row.candidate.handle)
const expectHandles = ['soon', 'later', 'hydra', 'sig', 'gamenest', 'code', 'jsready', 'older']
if (handles.join(',') !== expectHandles.join(',')) fail(`order ${handles.join(',')}`)

const hydra = rows.find((row) => row.candidate.handle === 'hydra')
if (!hydra || hydra.launch || hydra.tags.join(',') !== '即将启动') fail('hydra tags')
const code = rows.find((row) => row.candidate.handle === 'code')
if (!code || code.launch || !code.tags.includes('合约代码完成度高')) fail('contract tag')
const nest = rows.find((row) => row.candidate.handle === 'gamenest')
if (!nest?.tags.includes('游戏代码完成度高')) fail('game tag')
const js = rows.find((row) => row.candidate.handle === 'jsready')
if (!js?.tags.includes('站点/JS 完成度高')) fail('js tag')
if (rows.some((row) => row.launch && row.tags.length > 0)) fail('timed rows should not carry untimed tags')

const parsed = collectMonitorEvents({
  events: [
    {
      kind: 'site',
      at: '2026-10-21T00:00:00Z',
      handle: 'parsed',
      name: 'Parsed',
      site: { url: 'https://example.test/app', status: 'up', http_code: 200, is_file: { contract_code: 90 } },
    },
  ],
})
const parsedRows = upcomingLaunches(
  [candidate({ handle: 'parsed', name: 'Parsed', status: '开发中', listing: '未开盘' })],
  parsed,
  [],
  now,
)
if (parsedRows.length !== 1 || !parsedRows[0].tags.includes('合约代码完成度高')) fail('parsed site scrape')

const boner =
  'low confidence: feed-style site that embeds third-party token icons/posts; likely not this project\'s own CA; taken from a token-icon URL on the page (may be a third-party token); ca_gate: ERC20 verified: BONER dec=18'
const bonerZh = localizeMachineNote(boner)
const bonerExpected =
  '低置信：信息流站点嵌入第三方代币图标/帖子；多半不是本项目自有 CA；来自页面代币图标 URL（可能是第三方）；核验：已确认 ERC20（符号 BONER，精度 18）'
if (bonerZh !== bonerExpected) fail(`boner\n${bonerZh}`)

const colorful =
  'onchain_lock low via name_fuzzy:color; deployer=0x501ef174b66883ba40f92e6fb24bfb49331d4d4c; token=Vibrant Alpine Village Beneath a Colorful Sky / Vibrant Alpine Village Beneath a Colorful Sky; ca_gate: ERC20 verified: Vibrant Alpine Village Beneath a Colorful Sky dec=18'
const colorfulZh = localizeMachineNote(colorful)
const colorfulExpected =
  '链上锁定：低置信，依据名称模糊匹配 color；部署者 0x501ef174b66883ba40f92e6fb24bfb49331d4d4c；代币 Vibrant Alpine Village Beneath a Colorful Sky / Vibrant Alpine Village Beneath a Colorful Sky；核验：已确认 ERC20（符号 Vibrant Alpine Village Beneath a Colorful Sky，精度 18）'
if (colorfulZh !== colorfulExpected) fail(`colorful\n${colorfulZh}`)

const samples = [
  'ca_gate: ERC20 verified: HYDRA dec=18',
  'ca_gate: NFT contract (ERC721) — not a token CA',
  'ca_gate: NFT contract (ERC1155) — not a token CA',
  'ca_gate: SPL mint verified (owner Tokenz…, dec=6)',
  'ca_gate: eth_getCode empty / 7702 → EOA wallet',
  'ca_gate: not a valid Solana pubkey',
  'ca_gate: hex string (hash / git SHA), not a Solana address',
  'ca_gate: contract bytecode but no ERC20 decimals/symbol — not a token CA',
  'ca_gate: contract has decimals/symbol but missing ERC20 transfer/approve/allowance path — not a token CA',
  'ca_gate: account does not exist on Solana mainnet',
  'classified as EOA/wallet via eth_getCode',
  'classified as contract (3248 bytes)',
  'appears as a ?ref= referral parameter — likely a wallet, not a token CA',
  'address appears all-lowercase (taken from a URL); Solana is case-sensitive — verify exact mint',
  'onchain_lock medium via symbol:HATCH+name:hatch; deployer=0xabc; token=HATCH / Hatch',
  'onchain_lock low via name_fuzzy:pitch',
  'onchain_lock confirmed via wallet+token:symbol:SIEGE',
  'name_match_unconfirmed',
  '【非正式·官推未认 Processor(ERC-721)】watched wallet 0x8941 created 13:48 but @TapeRobot_bsc named 0x37e4/0xcd28; never confirmed; superseded_by=0xcd28c21d3382ec72d0693a7187eec0287f7e5174',
  '【合约CA】TapeOut监控 TapeRobot via x:@TapeRobot_bsc; creator=; tx=; ca_gate: ERC20 verified: TapeRobot dec=18',
  '【晶体管合约(ERC-1155)】TapeOut监控 TapeRobot via factory:tapeout:creator_watched',
  '同名非官方：创建者 0x2590782dd8c42f62b8e3b4ff788505fc64ed637e 不在监控钱包内，官推未确认',
  '官方TapeRobot·Processor(ERC-721)',
]
const banned = [
  /low confidence/i,
  /ca_gate/i,
  /ERC20 verified/i,
  /feed-style/i,
  /third-party/i,
  /likely not this/i,
  /token-icon/i,
  /classified as/i,
  /name_match_unconfirmed/i,
  /onchain_lock/i,
  /never confirmed/i,
  /case-sensitive/i,
  /referral parameter/i,
  /not a valid Solana/i,
  /hex string/i,
  /contract bytecode/i,
  /does not exist/i,
  /watched wallet/i,
  /superseded_by/i,
  /deployer=/i,
  /creator=/i,
  /via factory/i,
  /via x:/i,
  /not a token CA/i,
  /eth_getCode empty/i,
  /\bProcessor\b/,
]
for (const sample of samples) {
  const zh = localizeMachineNote(sample)
  for (const pattern of banned) {
    if (pattern.test(zh)) fail(`still english ${pattern} in ${zh}`)
  }
  if (zh === sample && /[A-Za-z]{4,}/.test(sample.replace(/ERC-?\d+|TapeOut|TapeRobot|HATCH|Hatch|SIEGE|Tokenz|EOA|SPL|mint/g, ''))) {
    fail(`unchanged ${sample}`)
  }
}

// Live automation data changes every few minutes. An untranslated phrase there is reported,
// but only blocks CI with STRICT_LIVE_DATA=1 so a new upstream wording cannot stop deploys.
const strictLive = process.env.STRICT_LIVE_DATA === '1'
const liveIssues: string[] = []
const live = JSON.parse(readFileSync(new URL('../public/data/ca_finds.json', import.meta.url), 'utf8')) as {
  finds?: Array<Record<string, unknown>>
  suspected_copycats?: Array<Record<string, unknown>>
  wallet_activity?: Array<Record<string, unknown>>
  launched_history?: Array<Record<string, unknown>>
}
const liveRows = [
  ...(live.finds ?? []),
  ...(live.suspected_copycats ?? []),
  ...(live.wallet_activity ?? []),
  ...(live.launched_history ?? []),
]
for (const row of liveRows) {
  for (const key of ['note', 'label_zh', 'label', 'confirm_basis_zh']) {
    const raw = row[key]
    if (typeof raw !== 'string' || !raw.trim()) continue
    const zh = localizeMachineNote(raw)
    for (const pattern of banned) {
      if (pattern.test(zh)) liveIssues.push(`${key} still english ${pattern} :: ${zh}`)
    }
  }
}
if (liveIssues.length > 0) {
  if (strictLive) fail(liveIssues[0])
  for (const issue of liveIssues) console.warn(`warning: live ca note ${issue}`)
}

const kept = localizeMachineNote('同名非官方：创建者 0xabc 不在监控钱包内，官推未确认')
if (!kept.includes('不在监控钱包内')) fail('chinese note changed')

console.log(`upcoming rows ${rows.length}; live ca notes checked ${liveRows.length}`)
