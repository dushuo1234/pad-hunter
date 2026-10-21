import { readFileSync } from 'node:fs'
import {
  alertableFinds,
  caSourceBadges,
  caSourceLabel,
  compareFindsByNewest,
  findIsLaunched,
  indexLaunchedProjects,
  lockIsLaunched,
  parseCaFinds,
} from '../src/utils/caFinds.ts'

function fail(message: string): never {
  throw new Error(message)
}

const expected: Record<string, string> = {
  'js:https://colorapp.com/assets/color/live.js': '官网JS',
  'site:https://example.com/': '官网',
  'site:https://x.com/TheHydraAgent': '官推X',
  'inline:https://bao.la/': '内联页面',
  'html:https://bao.la/': '官网',
  x_post: '官推X',
  'x:@TapeRobot_bsc': '官推X',
  onchain_lock: '链上锁定扫描',
  'factory:tapeout:creator_watched': '链上工厂',
  'tapeout:superseded': '链上工厂',
  'tg:https://t.me/padhunter': 'Telegram',
  'site:https://t.me/padhunter': 'Telegram',
  js: '官网JS',
  site: '官网',
  x: '官推X',
  tg: 'Telegram',
  'on-chain': '链上',
}

for (const [raw, label] of Object.entries(expected)) {
  const got = caSourceLabel(raw)
  if (got !== label) fail(`${raw} → ${got}, want ${label}`)
  if (/https?:|js:|inline:|onchain_lock|factory:|x_post|site:/.test(got)) fail(`raw leak in ${got}`)
}

const badges = caSourceBadges(
  ['factory:tapeout:creator_watched', 'x:@TapeRobot_bsc'],
  'https://x.com/TapeRobot_bsc/status/1',
)
if (badges.map((badge) => badge.label).join(',') !== '链上工厂,官推X') fail(`badges ${badges.map((badge) => badge.label).join(',')}`)
if (badges[1]?.href !== 'https://x.com/TapeRobot_bsc') fail(`x href ${badges[1]?.href}`)

const live = parseCaFinds(JSON.parse(readFileSync(new URL('../public/data/ca_finds.json', import.meta.url), 'utf8')))
const launched = JSON.parse(readFileSync(new URL('../public/data/launched.json', import.meta.url), 'utf8')) as {
  items?: { handle?: string; project?: string; ca?: string | null }[]
}
const index = indexLaunchedProjects(launched.items ?? [])
const rawHistory = JSON.parse(readFileSync(new URL('../public/data/ca_finds.json', import.meta.url), 'utf8')) as {
  launched_history?: unknown[]
}

if (live.launchedHistory.length !== (rawHistory.launched_history?.length ?? 0)) {
  fail(`history ${live.launchedHistory.length}`)
}
if (live.launchedHistory.some((row) => !row.archived || row.alertOk)) fail('history alert')
if (alertableFinds(live.launchedHistory).length !== 0) fail('history alertable')
if (!live.launchedHistory.some((row) => row.caStatus === 'confirmed' && findIsLaunched(row, index))) fail('confirmed history missing')

const hydra = live.finds.find((row) => row.handle.toLowerCase() === 'thehydraagent')
if (!hydra || findIsLaunched(hydra, index)) fail('hydra should stay active')
if (caSourceLabel(hydra.source) !== '官推X') fail(`hydra source ${caSourceLabel(hydra.source)}`)

for (const row of [...live.finds, ...live.suspectedCopycats, ...live.launchedHistory]) {
  for (const badge of caSourceBadges(row.sourceRefs, row.evidence_url)) {
    if (/https?:|js:|inline:|onchain_lock|factory:|x_post|site:|tapeout:/.test(badge.label)) fail(`leak ${badge.label} from ${row.source}`)
  }
  if (row.source && !/[\u4e00-\u9fff]/.test(caSourceLabel(row.source)) && caSourceLabel(row.source) !== 'Telegram') {
    fail(`not chinese ${row.source} → ${caSourceLabel(row.source)}`)
  }
}

const olderActive = { ...hydra, detected_at: '2020-01-01T00:00:00+08:00', archived: false }
const newerLaunched = live.launchedHistory.find((row) => row.caStatus === 'candidate')
if (!newerLaunched) fail('no launched candidate')
const ordered = [newerLaunched, olderActive].sort(compareFindsByNewest)
const activeFirst = [...ordered].sort((a, b) => Number(findIsLaunched(a, index)) - Number(findIsLaunched(b, index)) || compareFindsByNewest(a, b))
if (findIsLaunched(activeFirst[0], index) || !findIsLaunched(activeFirst[1], index)) fail('launched did not sink')
if (compareFindsByNewest(newerLaunched, olderActive) > 0) fail('newer launched should sort ahead inside its bucket')

if (!lockIsLaunched({ id: 'k:taperobot_bsc', project: '', handle: 'taperobot_bsc', url: '', aliases: ['k:taperobot_bsc', 'h:taperobot_bsc'] }, index)) {
  fail('tape lock should be launched')
}

console.log('ca presentation checks ok', {
  history: live.launchedHistory.length,
  activeFinds: live.finds.length,
  hydra: caSourceLabel(hydra.source),
})
