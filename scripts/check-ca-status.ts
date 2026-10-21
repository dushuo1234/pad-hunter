import { readFileSync } from 'node:fs'
import { alertableFinds, lockForFind, parseCaFinds } from '../src/utils/caFinds.ts'
import { matchLaunched, readLaunched } from '../src/utils/launched.ts'

const live = parseCaFinds(JSON.parse(readFileSync(new URL('../public/data/ca_finds.json', import.meta.url), 'utf8')))
const launched = readLaunched(JSON.parse(readFileSync(new URL('../public/data/launched.json', import.meta.url), 'utf8')))
const alerts = alertableFinds(live.finds, launched.items)

function fail(message: string): never {
  throw new Error(message)
}

if (live.schemaVersion !== 2) fail(`schema ${live.schemaVersion}`)
if (live.statusCounts.confirmed !== 0) fail(`confirmed count ${live.statusCounts.confirmed}`)
if (live.finds.some((row) => row.caStatus === 'confirmed')) fail('active confirmed rows')
if (alerts.length !== 0) fail(`alerts ${alerts.length}`)
if (live.finds.some((row) => row.caStatus === 'not_ca' && row.alertOk)) fail('not_ca alerted')
if (live.suspectedCopycats.length !== 10) fail(`copycats ${live.suspectedCopycats.length}`)
if (live.suspectedCopycats.some((row) => row.alertOk || row.creatorWatched !== false)) fail('copycat flags')
if (live.suspectedCopycats.some((row) => row.caStatus !== 'suspected_copycat')) fail('copycat status')
if (live.supersededArchive.length !== 2) fail(`superseded ${live.supersededArchive.length}`)
if (live.supersededArchive.some((row) => row.alertOk || !row.supersededBy)) fail('superseded alert')
if (live.launchedArchive.length !== 4) fail(`launched archive ${live.launchedArchive.length}`)
if (live.launchedArchive.some((row) => row.alertOk || row.caStatus !== 'confirmed' || !row.archived)) fail('archive flags')
const tape = live.launchedArchive.filter((row) => row.projectKey === 'taperobot_bsc')
if (tape.length !== 3) fail(`tape archive ${tape.length}`)
if (tape.some((row) => matchLaunched(launched.items, row)?.handle !== 'TapeRobot_bsc')) fail('tape launched match')
const processor = tape.find((row) => row.caRole === 'processor')
if (!processor?.pairedWith) fail('processor pair')
const token = tape.find((row) => row.caRole === 'token')
if (!token || token.provenance !== 'official_x' || token.provenanceZh !== '官推确认') fail('token provenance')
if (!token.officialXUrl || !token.confirmBasisZh) fail('token basis')
if (!token.caLocked || !token.lockUrl.includes('/status/')) fail('token lock')
if (token.officialXUrl === token.lockUrl) fail('token tweet and lock tweet collapsed')
if (!live.locks.some((lock) => lock.url.includes('/status/'))) fail('project lock')
if (!lockForFind(live.locks, token)?.url.includes('/status/')) fail('token lock join')
if (live.walletActivity.some((row) => row.alertOk)) fail('live activity alert')
const copyTape = live.suspectedCopycats.filter((row) => row.handle === 'TapeOutWatch')
const copyOther = live.suspectedCopycats.filter((row) => row.handle !== 'TapeOutWatch')
if (copyTape.length !== 8 || copyOther.length !== 2) fail('copycat split')
if (copyTape.some((row) => matchLaunched(launched.items, row)?.project !== 'TapeRobot')) fail('copycat launched')
if (copyOther.some((row) => matchLaunched(launched.items, row))) fail('open copycat marked launched')
if (matchLaunched(launched.items, { handle: 'TapePool', project: 'TapePool' })) fail('tapeout neighbor matched')
if (alertableFinds(tape, launched.items).length !== 0) fail('archive alertable')

const synthetic = parseCaFinds({
  schema_version: 2,
  status_counts: { confirmed: 1, candidate: 0, superseded: 0, not_ca: 0 },
  suspected_copycat_count: 1,
  finds: [
    {
      project: 'TapeRobot·TapeOut监控',
      handle: 'TapeOutWatch',
      chain: 'bsc',
      address: '0xaaa',
      ca_status: 'confirmed',
      ca_status_zh: '已确认CA',
      provenance: 'official_x',
      provenance_zh: '官推确认',
      confirm_basis_zh: '官推确认',
      official_x_url: 'https://x.com/TapeRobot_bsc/status/1',
      ca_role: 'token',
      alert_ok: true,
      ca_locked: true,
      locked_by_official_x_url: 'https://x.com/TapeRobot_bsc/status/1',
      confidence: 'high',
    },
    {
      project: '【疑似山寨】TapeRobot',
      handle: 'TapeOutWatch',
      chain: 'bsc',
      address: '0xbbb',
      ca_status: 'suspected_copycat',
      ca_status_zh: '疑似山寨',
      alert_ok: true,
      creator_watched: false,
    },
  ],
  suspected_copycats: [],
  wallet_activity: [
    {
      project: 'TapeRobot',
      handle: 'TapeRobot_bsc',
      chain: 'bsc',
      address: '0xccc',
      tx: '0xddd',
      note: '监控钱包转账',
      alert_ok: true,
      ca_locked: true,
    },
  ],
  locked_projects: [
    {
      project: 'TapeRobot',
      handle: 'TapeOutWatch',
      ca_locked: true,
      locked_by_official_x_url: 'https://x.com/TapeRobot_bsc/status/1',
    },
  ],
})

if (synthetic.locks.length !== 1) fail(`locks ${synthetic.locks.length}`)
if (synthetic.locks[0]?.url !== 'https://x.com/TapeRobot_bsc/status/1') fail('lock url')
if (synthetic.walletActivity.length !== 1) fail('activity hidden')
if (synthetic.walletActivity[0]?.alertOk) fail('activity alerted')
if (synthetic.walletActivity[0]?.caLocked !== true) fail('activity not locked')
if (alertableFinds(synthetic.finds).length !== 1) fail('synthetic alerts')
if (alertableFinds(synthetic.finds, [{ project: 'TapeRobot', handle: 'TapeRobot_bsc', chain: '', category: '', xUrl: '', sites: [], listingAt: null, ca: null, caChain: null, reason: '', evidence: '', removedAt: '' }]).length !== 0) {
  fail('launched synthetic still alerted')
}
if (synthetic.suspectedCopycats.length !== 1) fail('synthetic copycat missing')
if (synthetic.suspectedCopycats[0]?.alertOk) fail('copycat forced alert')
if (!synthetic.finds[0]?.caLocked || synthetic.finds[0].lockUrl !== 'https://x.com/TapeRobot_bsc/status/1') fail('row lock')

console.log('ca status checks ok', {
  confirmed: live.statusCounts.confirmed,
  launchedArchive: live.launchedArchive.length,
  copycats: live.suspectedCopycats.length,
  superseded: live.supersededArchive.length,
  alerts: alerts.map((row) => row.caRole),
})
