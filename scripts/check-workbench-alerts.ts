import { readFileSync } from 'node:fs'
import { applyParsedAlertEvent, ALERT_HIGHLIGHT_MS, ALERT_POLL_MS, ALERT_UI, alertFeedChanged, alertsByHandle, CONSOLE_LINE_LIMIT, consoleLines, consoleVisibleText, flashingAlertIds, flashingReminderCount, formatAlertAgo, FORTUNE_CHIME_DEBOUNCE_MS, isConfirmedCa, loadStoredWorkbenchAlerts, mergeAlertIncremental, normalizeAlertList, parseWorkbenchAlert, parseWorkbenchAlertsPayload, pickCa, pickFortuneVoice, planFreshAlert, presentCa, reminderCanFlash, reminderTitle, reminderViews, reminderVisibleText, remindersAllowed, rowAttentionTone, shouldPlayChime, shouldToastAlert, stripLeadName, WB_ALERTS_LIMIT, WB_ALERTS_STORAGE_KEY, WORKBENCH_ALERTS_PATH, type WorkbenchAlert } from '../src/utils/workbenchAlerts.ts'
import { parseSocketMessage } from '../src/utils/workbenchSocket.ts'

function fail(message: string): never {
  throw new Error(message)
}

const fixture = JSON.parse(readFileSync(new URL('./fixtures/workbench_alerts.json', import.meta.url), 'utf8')) as {
  alerts: unknown[]
  dry_run_message: unknown
}

const KIND = ['x_post', 'site_time', 'ca', 'ca_signal', 'js_address', 'site_change', 'js_change']
const STATUS = ['confirmed', 'candidate', 'suspected_copycat', 'nft', 'superseded', 'unconfirmed']

const parsed = fixture.alerts.map((row, index) => {
  const alert = parseWorkbenchAlert(row)
  if (!alert) fail(`fixture row ${index} did not parse`)
  return alert
})

const kinds = new Set(parsed.map((alert) => alert.kind))
for (const kind of KIND) {
  if (!kinds.has(kind as WorkbenchAlert['kind'])) fail(`fixture missing kind ${kind}`)
}
const statuses = new Set(parsed.map((alert) => alert.ca_status).filter(Boolean))
for (const status of STATUS) {
  if (!statuses.has(status as WorkbenchAlert['ca_status'])) fail(`fixture missing ca_status ${status}`)
}

const now = Date.parse('2026-10-24T00:00:00+08:00')

for (const alert of parsed) {
  const badge = presentCa(alert)
  if (isConfirmedCa(alert)) {
    if (badge.label !== '已确认CA' || badge.tone !== 'ok' || !badge.confirmed) fail(`${alert.id} should render 已确认CA`)
  } else if (badge.label.includes('已确认') || badge.tone === 'ok' || badge.confirmed) {
    fail(`${alert.id} looked confirmed: ${badge.label}`)
  }
  if ((alert.ca_status === 'nft' || alert.ca_status === 'suspected_copycat') && !badge.label.includes('不算CA')) {
    fail(`${alert.id} ${alert.ca_status} should say 不算CA, got ${badge.label}`)
  }
}

const grouped = alertsByHandle(parsed)
const caravan = reminderViews(grouped.get('caravanrh') ?? [], now)
if (caravan.map((view) => view.key).join(',') !== 'soon,ca,change') fail(`caravan lines ${caravan.map((view) => view.key).join(',')}`)
const caravanSoon = caravan.find((view) => view.key === 'soon')
const caravanCa = caravan.find((view) => view.key === 'ca')
const caravanChange = caravan.find((view) => view.key === 'change')
if (!caravanSoon?.body.includes('官推说即将开始')) fail('soon should be the newer x_post')
if (caravanSoon.body.split('10/24 12:00（北京时间）').length !== 2) fail('start display duplicated or missing')
if (caravanSoon.delay) fail('caravan soon is not a delay')
if (caravanCa?.badge?.label !== '已确认CA' || !caravanCa.copyable) fail('caravan ca must be the confirmed row, not the newer signal')
if (!caravanCa.address.startsWith('0x1111')) fail('confirmed address')
if (caravanChange?.body !== '官网内容有变动') fail(`change body ${caravanChange?.body}`)

const delay = reminderViews(grouped.get('delayproj') ?? [], now)
if (!delay[0]?.delay || delay[0].body.includes('【')) fail('delay badge or name prefix')
if (delay[0].body.includes('11/01 20:00（北京时间）') === false) fail('delay should show the clock')

const falseOk = reminderViews(grouped.get('falseok') ?? [], now)
if (falseOk[0]?.badge?.label !== '待核验') fail(`false ok badge ${falseOk[0]?.badge?.label}`)
if (reminderVisibleText(falseOk).includes('已确认')) fail('confirmed without alert_ok rendered 已确认')

const nft = reminderViews(grouped.get('nftproj') ?? [], now)
if (!nft[0]?.badge?.label.includes('不算CA') || nft[0].badge.label.includes('已确认') || nft[0].copyable) fail('nft presentation')
const copycat = reminderViews(grouped.get('copyproj') ?? [], now)
if (!copycat[0]?.badge?.label.includes('不算CA') || copycat[0].badge.tone === 'ok') fail('copycat presentation')
if (reminderViews(grouped.get('oldproj') ?? [], now)[0]?.badge?.label !== '旧CA') fail('superseded')
if (reminderViews(grouped.get('candproj') ?? [], now)[0]?.badge?.label !== '待核验') fail('candidate')
if (reminderViews(grouped.get('unconfproj') ?? [], now)[0]?.badge?.label !== '待核验') fail('unconfirmed')
if (reminderViews(grouped.get('signalonly') ?? [], now)[0]?.badge?.label !== '待核验') fail('ca_signal fallback')
if (reminderViews(grouped.get('jsaddr') ?? [], now)[0]?.key !== 'ca') fail('js_address fallback')
if (reminderViews(grouped.get('jschange') ?? [], now)[0]?.body !== '官网脚本有变动') fail('js change')

const flip = grouped.get('flipca') ?? []
const flipCa = pickCa(flip)
if (flipCa?.ca_status !== 'nft') fail('same address must keep the newest status')
const flipView = reminderViews(flip, now).find((view) => view.key === 'ca')
if (!flipView?.badge?.label.includes('不算CA') || flipView.badge.label.includes('已确认')) fail('flipped address still looks confirmed')

const agoNow = Date.parse('2026-10-24T00:04:00+08:00')
if (formatAlertAgo('2026-10-24T00:01:00+08:00', agoNow) !== '3 分钟前') fail('relative time')

if (stripLeadName('【CaravanRH】官推说即将开始') !== '官推说即将开始') fail('strip name')

const soon = parsed.find((alert) => alert.id === 'aaaaaaaaaaaaaaa1')
const baseline = parsed.find((alert) => alert.id === 'aaaaaaaaaaaaaab7')
const confirmed = parsed.find((alert) => alert.id === 'aaaaaaaaaaaaaaa3')
const gated = parsed.find((alert) => alert.id === 'aaaaaaaaaaaaaaa8')
const nftAlert = parsed.find((alert) => alert.id === 'aaaaaaaaaaaaaab1')
const delayed = parsed.find((alert) => alert.id === 'aaaaaaaaaaaaaaa7')
if (!soon || !baseline || !confirmed || !gated || !nftAlert || !delayed) fail('missing ids')
if (!shouldToastAlert(soon, now)) fail('soon within 24h should toast')
if (shouldToastAlert(delayed, now)) fail('start beyond 24h should not toast')
if (shouldToastAlert(baseline, now)) fail('baseline should not toast')
if (!shouldToastAlert(confirmed, now)) fail('confirmed ca should toast')
if (shouldToastAlert(gated, now) || shouldToastAlert(nftAlert, now)) fail('unready ca should not toast')
const fresh = planFreshAlert(soon, now)
if (!fresh.unread || fresh.highlightUntil - now !== ALERT_HIGHLIGHT_MS || !fresh.toast) fail('fresh plan')
if (planFreshAlert(baseline, now).unread || planFreshAlert(baseline, now).toast) fail('baseline plan')

if (!remindersAllowed({ pinned: true, launched: false })) fail('pinned row shows reminders')
if (remindersAllowed({ pinned: false, launched: false }) || remindersAllowed({ pinned: true, launched: true })) {
  fail('launched or unpinned reminders must hide')
}

const dry = parseSocketMessage(fixture.dry_run_message)
if (dry.kind !== 'ignore') fail('dry_run message must be ignored')
let feed = applyParsedAlertEvent([], dry)
if (feed.some((alert) => alert.id === 'deadbeefdeadbeef')) fail('dry_run alert was stored')

const hello = parseSocketMessage({
  type: 'workbench_alerts',
  event: 'hello',
  state: { updated_at: '2026-10-24T00:03:00+08:00', count: parsed.length, items: fixture.alerts },
})
if (hello.kind !== 'alerts_snapshot') fail('hello kind')
feed = applyParsedAlertEvent([{ ...soon, id: 'eeeeeeeeeeeeeee1' }], hello)
if (feed.some((alert) => alert.id === 'eeeeeeeeeeeeeee1')) fail('snapshot must replace')
if (feed.filter((alert) => alert.id === soon.id).length !== 1) fail('snapshot duplicated an id')

const again = mergeAlertIncremental(feed, [soon, soon])
if (again.added.length !== 0 || again.alerts.filter((alert) => alert.id === soon.id).length !== 1) fail('same id twice')
const extra = parseWorkbenchAlert({
  id: 'cccccccccccccccc',
  handle: 'CaravanRH',
  kind: 'x_post',
  ts: '2026-10-24T00:08:00+08:00',
  summary: '【CaravanRH】又一条官推',
  baseline: false,
})
if (!extra) fail('extra parse')
const prepended = mergeAlertIncremental(again.alerts, [extra])
if (prepended.alerts[0]?.id !== extra.id || prepended.added.length !== 1) fail('new id should be inserted first')
if (prepended.alerts.filter((alert) => alert.id === extra.id).length !== 1) fail('new id duplicated')

const many: WorkbenchAlert[] = []
for (let index = 0; index < WB_ALERTS_LIMIT + 5; index += 1) {
  many.push({
    ...soon,
    id: index.toString(16).padStart(16, '0'),
    ts: new Date(now - index * 60_000).toISOString(),
  })
}
const capped = normalizeAlertList(many)
if (capped.length !== WB_ALERTS_LIMIT) fail(`cap ${capped.length}`)
if (capped[0]?.id !== many[0]?.id) fail('cap should keep the newest')
if (capped.some((alert) => alert.id === many[WB_ALERTS_LIMIT + 4]?.id)) fail('oldest should be dropped')

const quiet = { ...soon, id: 'ddddddddddddddd1', handle: 'QuietProj', summary: '【QuietProj】保持安静' }
const loaded = loadStoredWorkbenchAlerts(JSON.stringify({ alerts: [soon, soon, extra, quiet], unread: ['@CaravanRH', 'caravanrh'] }))
if (loaded.alerts.filter((alert) => alert.id === soon.id).length !== 1) fail('storage dedupe')
if (loaded.unread.join(',') !== 'caravanrh') fail(`unread ${loaded.unread.join(',')}`)
if (loaded.readIds.includes(soon.id) || loaded.readIds.includes(extra.id)) fail('legacy unread handle must stay unread')
if (!loaded.readIds.includes(quiet.id)) fail('other handles in an old blob should stay quiet')
const backlog = loadStoredWorkbenchAlerts(JSON.stringify({ alerts: [soon] }))
if (!backlog.seeded || !backlog.readIds.includes(soon.id)) fail('history without readIds should not start blinking')
const explicit = loadStoredWorkbenchAlerts(JSON.stringify({ alerts: [soon], readIds: [] }))
if (explicit.readIds.length !== 0) fail('an empty readIds list means nothing is acknowledged')

const polled = parseWorkbenchAlertsPayload({
  updated_at: '2026-10-24T00:03:00+08:00',
  count: 1,
  items: [fixture.alerts[0]],
})
if (polled.length !== 1 || polled[0]?.handle !== 'CaravanRH') fail('GET payload')

if (WB_ALERTS_STORAGE_KEY !== 'ph.wbAlerts.v1') fail('storage key')
if (ALERT_POLL_MS !== 60_000) fail('poll interval')
if (ALERT_HIGHLIGHT_MS !== 30_000) fail('highlight window')
if (WORKBENCH_ALERTS_PATH !== '/v1/workbench/alerts') fail('alerts path')

const englishSentence = /[A-Za-z]{2,}(?:[^A-Za-z\u4e00-\u9fff0-9]+[A-Za-z]{2,}){2,}/
const banned = /\b(confirmed|candidate|unconfirmed|copycat|baseline|dry_run|alert_ok|suspected|x_post|site_time|js_address|ca_signal|site_change|js_change)\b/i

function prose(text: string, alert?: WorkbenchAlert): string {
  let next = text
  if (alert?.quote) next = next.split(alert.quote).join(' ')
  if (alert?.evidence_url) next = next.split(alert.evidence_url).join(' ')
  if (alert?.address) next = next.split(alert.address).join(' ')
  return next.replace(/https?:\/\/\S+/g, ' ').replace(/0x[a-fA-F0-9]+/g, ' ')
}

for (const alert of parsed) {
  const views = reminderViews([alert], now)
  const visible = reminderVisibleText(views)
  const shown = views.map((view) => `${view.label} ${view.body} ${view.badge?.label ?? ''} ${view.ago}`).join('\n')
  if (alert.quote && shown.includes(alert.quote)) fail(`${alert.id} quote leaked into the line`)
  if (alert.evidence_url && shown.includes('http')) fail(`${alert.id} url leaked into the line`)
  const checked = prose(visible, alert)
  if (englishSentence.test(checked)) fail(`${alert.id} english sentence: ${checked}`)
  if (banned.test(checked)) fail(`${alert.id} english token: ${checked}`)
}

const ui = Object.values(ALERT_UI).join('\n')
if (englishSentence.test(ui) || banned.test(ui)) fail(`ui copy ${ui}`)

if (reminderCanFlash(baseline) || reminderCanFlash(nftAlert)) fail('baseline and 不算CA must not flash')
const copycatAlert = parsed.find((alert) => alert.ca_status === 'suspected_copycat')
if (!copycatAlert || reminderCanFlash(copycatAlert)) fail('copycat must not flash')
if (!reminderCanFlash(soon) || !reminderCanFlash(confirmed)) fail('soon and confirmed CA should be able to flash')
if (!caravanSoon?.urgent || caravanSoon.tone !== 'soon') fail('soon line tone')
if (caravanCa?.tone !== 'ok' || !caravanCa.urgent) fail('confirmed line should be the green urgent tone')
if (caravanChange?.tone !== 'change') fail('change tone')
if (nft[0]?.urgent) fail('nft line must not be urgent')
if (!falseOk[0]?.urgent || falseOk[0].tone !== 'warn') fail('pending CA can flash, but not as 已确认')
if (rowAttentionTone(caravan, new Set()) !== 'soon') fail('a flashing 即将开始 line sets the row color')
if (rowAttentionTone(nft, new Set()) !== 'muted') fail('不算CA row stays muted')

const noneRead = new Set<string>()
if (flashingReminderCount([soon, nftAlert, baseline], noneRead) !== 1) fail('only the urgent unread alert counts')
if (flashingReminderCount([soon], new Set([soon.id])) !== 0) fail('a read id stops the count')
if (flashingReminderCount([soon], noneRead, { pinned: new Set(['caravanrh']), launched: new Set(['caravanrh']) }) !== 0) {
  fail('launched projects drop out of the count')
}
if (reminderTitle(3, '工作台 · 台子雷达', true) !== '(3) 新提醒') fail('tab title blink')
if (reminderTitle(3, '工作台 · 台子雷达', false) !== '工作台 · 台子雷达') fail('tab title between blinks')
if (reminderTitle(0, '工作台 · 台子雷达', true) !== '工作台 · 台子雷达') fail('quiet tab title')
if (reminderTitle(3, '工作台 · 台子雷达', true, true) !== '(3) 新提醒 · 工作台 · 台子雷达') fail('reduced-motion title')

const board = consoleLines(parsed, noneRead)
const soonConsole = board.find((line) => line.id === soon.id)
const nftConsole = board.find((line) => line.id === nftAlert.id)
const baseConsole = board.find((line) => line.id === baseline.id)
const confirmedConsole = board.find((line) => line.id === confirmed.id)
if (!soonConsole?.flash || soonConsole.label !== '即将开始') fail('console soon line should blink')
if (soonConsole.evidenceUrl !== soon.evidence_url || soonConsole.quote !== soon.quote) fail('console keeps the source quote and link')
if (!confirmedConsole?.flash || confirmedConsole.label !== '已确认CA') fail('console confirmed line')
if (!confirmedConsole.copyAddress.startsWith('0x1111')) fail('confirmed CA stays copyable in the console')
if (!nftConsole || nftConsole.flash || !nftConsole.label.includes('不算CA') || nftConsole.label.includes('已确认')) {
  fail('console 不算CA stays muted')
}
if (nftConsole.copyAddress) fail('不算CA is not copyable from the console')
if (!baseConsole || baseConsole.flash) fail('console baseline stays quiet')
if (board[0] && board[1] && Date.parse(board[0].ts) < Date.parse(board[1].ts) && board[0].flash === board[1].flash) {
  fail('console keeps newest first within the same blink group')
}
const hiddenConsole = consoleLines([soon], noneRead, { pinned: new Set(['caravanrh']), launched: new Set(['caravanrh']) })
if (hiddenConsole.length !== 0) fail('launched alerts stay out of the console')
const perProject = consoleLines([soon, nftAlert], noneRead, {
  pinned: new Set(['caravanrh', 'nftproj']),
  launched: new Set(),
  handle: '@CaravanRH',
})
if (perProject.length !== 1 || perProject[0]?.id !== soon.id) fail('a project console must only list that project')
const readConsole = consoleLines([soon, confirmed], new Set([soon.id]))
if (readConsole[0]?.id !== confirmed.id || readConsole[0]?.flash !== true || readConsole[1]?.flash !== false) {
  fail('unread lines lead the console')
}
const consoleText = consoleVisibleText(board)
for (const alert of parsed) {
  const checked = prose(consoleText, alert)
  if (englishSentence.test(checked)) fail(`console english sentence: ${checked}`)
  if (banned.test(checked)) fail(`console english token: ${checked}`)
}
if (flashingAlertIds([soon, nftAlert], noneRead).join(',') !== soon.id) fail('flash ids skip 不算CA')

const overflow: WorkbenchAlert[] = []
for (let index = 0; index < CONSOLE_LINE_LIMIT + 5; index += 1) {
  overflow.push({
    ...baseline,
    id: index.toString(16).padStart(16, 'b'),
    baseline: true,
    ts: new Date(now - index * 60_000).toISOString(),
  })
}
overflow.push({ ...soon, id: 'eeeeeeeeeeeeeee2', ts: new Date(now - 86_400_000).toISOString() })
const windowed = consoleLines(overflow, noneRead)
if (windowed.length !== CONSOLE_LINE_LIMIT) fail(`console window ${windowed.length}`)
if (windowed[0]?.id !== 'eeeeeeeeeeeeeee2' || !windowed[0]?.flash) fail('an older unread line stays at the top of the console')

for (const file of [
  '../src/utils/workbenchAlerts.ts',
  '../src/utils/workbenchAlertStore.ts',
  '../src/utils/workbenchChime.ts',
  '../src/components/WorkbenchReminders.tsx',
  '../src/components/WorkbenchAlertConsole.tsx',
  '../src/components/WorkbenchAlertToasts.tsx',
  '../src/hooks/useWorkbenchAlerts.ts',
]) {
  const source = readFileSync(new URL(file, import.meta.url), 'utf8')
  if (/\blisting_at\b/.test(source)) fail(`${file} invents listing_at`)
}

const api = readFileSync(new URL('../src/utils/workbenchApi.ts', import.meta.url), 'utf8')
if (!api.includes('X-Pad-Hunter-Token') || !api.includes('WORKBENCH_ALERTS_PATH')) fail('alerts GET must use the token header')

const css = readFileSync(new URL('../src/index.css', import.meta.url), 'utf8')
if (!css.includes('prefers-reduced-motion') || !css.includes('wb-row-flash') || !css.includes('wb-console') || !css.includes('wb-dot-flash')) {
  fail('flash styles missing')
}
const consoleSource = readFileSync(new URL('../src/components/WorkbenchAlertConsole.tsx', import.meta.url), 'utf8')
if (!consoleSource.includes('markWorkbenchAlertIdsRead') || !consoleSource.includes('工作台:~$')) fail('shared console must ack every flashing id')
if (!consoleSource.includes('handle')) fail('per-project console missing')
const reminderSource = readFileSync(new URL('../src/components/WorkbenchReminders.tsx', import.meta.url), 'utf8')
if (!reminderSource.includes('bg-emerald-600') || !reminderSource.includes('bg-orange-600') || !reminderSource.includes('bg-sky-600') || !reminderSource.includes('bg-amber-400')) {
  fail('solid reminder pills')
}
if (reminderSource.includes('bg-emerald-50')) fail('confirmed badge is still pale')
const pageSource = readFileSync(new URL('../src/pages/WorkbenchPage.tsx', import.meta.url), 'utf8')
const tableAt = pageSource.indexOf('<table')
const sharedAt = pageSource.indexOf('<WorkbenchAlertConsole')
const projectAt = pageSource.indexOf('<WorkbenchAlertConsole', sharedAt + 1)
if (sharedAt < 0 || projectAt < 0 || tableAt < 0 || sharedAt > tableAt || projectAt < tableAt) {
  fail('need the shared console above the list and a console inside each row')
}
if (pageSource.includes('<WorkbenchReminders') || pageSource.includes('wb-row-flash') || pageSource.includes('ALERT_UI.fresh')) {
  fail('realtime lines and flashing chips must not sit on the project row')
}
if (!pageSource.includes('简介') || !pageSource.includes('官网') || !pageSource.includes('X ')) {
  fail('project row keeps 简介, 官网, and X outside the console')
}
if (!pageSource.includes('pinned={pinnedKeys}') || !pageSource.includes('handle={item.handle}')) {
  fail('shared console and per-project console must both be wired')
}
if (pageSource.includes('wb-console-span') || pageSource.includes('100cqw') || css.includes('100cqw') || css.includes('container-type')) {
  fail('console width must not depend on container query units')
}
if (!pageSource.includes('wb-project') || !pageSource.includes('wb-h-scroll')) fail('project row scroll must stay inside the content column')
const projectChunk = pageSource.slice(Math.max(0, projectAt - 180), projectAt)
if (/<td[\s>]/.test(projectChunk) || projectChunk.includes('colSpan')) fail('project console is still inside the scrolling table')
if (!css.includes('width: 100%') || !css.includes('.wb-console')) fail('consoles must fill the content column')
const headerSource = readFileSync(new URL('../src/components/Header.tsx', import.meta.url), 'utf8')
if (!headerSource.includes('条未读提醒')) fail('nav unread count')

if (ALERT_UI.fortune !== '要发财啦') fail('fortune phrase')
if (!shouldPlayChime(0, FORTUNE_CHIME_DEBOUNCE_MS)) fail('a chime is due once the debounce window has elapsed')
if (shouldPlayChime(1000, 1000 + FORTUNE_CHIME_DEBOUNCE_MS - 1)) fail('a burst inside the debounce window stays quiet')
if (!shouldPlayChime(1000, 1000 + FORTUNE_CHIME_DEBOUNCE_MS)) fail('the next burst after the window may play')
if (alertFeedChanged([soon], [soon])) fail('identical alerts are not a new chime')
if (!alertFeedChanged([soon], [soon, confirmed])) fail('a new alert id is a chime')
if (!alertFeedChanged([soon], [{ ...soon, summary: `${soon.summary}更` }])) fail('changed alert content is a chime')
if (alertFeedChanged([soon, confirmed], [soon])) fail('removing an alert without new content stays quiet')
const girl = pickFortuneVoice([
  { lang: 'en-US', name: 'David', voiceURI: 'David male' },
  { lang: 'zh-CN', name: 'Microsoft Xiaoxiao Online', voiceURI: 'Xiaoxiao' },
  { lang: 'zh-CN', name: 'Microsoft Yunyang', voiceURI: 'Yunyang' },
])
if (girl?.name !== 'Microsoft Xiaoxiao Online') fail('zh-CN girl voice wins')
if (pickFortuneVoice([{ lang: 'en-US', name: 'David', voiceURI: 'male' }]) != null) fail('a non-Chinese voice is not a fortune voice')

const chimeSource = readFileSync(new URL('../src/utils/workbenchChime.ts', import.meta.url), 'utf8')
if (!chimeSource.includes('speechSynthesis') || !chimeSource.includes('pointerdown') || !chimeSource.includes('keydown')) {
  fail('chime must unlock on a gesture and speak with speechSynthesis')
}
if (!chimeSource.includes('ALERT_UI.fortune') || chimeSource.includes('.cancel(')) fail('chime speaks the fortune phrase without cutting other speech')
const storeSource = readFileSync(new URL('../src/utils/workbenchAlertStore.ts', import.meta.url), 'utf8')
if (!storeSource.includes('noteWorkbenchAlertChime') || !storeSource.includes('chimeIfContentChanged')) fail('store must chime when alert content changes')
const ackStart = storeSource.indexOf('export function markWorkbenchAlertsRead')
const ackEnd = storeSource.indexOf('export function getWorkbenchAlertSnapshot')
const ackSlice = storeSource.slice(ackStart, ackEnd)
if (ackStart < 0 || ackEnd < 0 || ackSlice.includes('noteWorkbenchAlertChime') || ackSlice.includes('chimeIfContentChanged')) {
  fail('acknowledging an alert must not play the chime')
}

console.log(`workbench alert checks ok (${parsed.length} fixture rows)`)
