import { localizeMachineNote } from '../src/utils/caNoteZh.ts'
import {
  localizeEventsNote,
  localizeProbeError,
  localizeTimelineText,
  timelineHealthLabel,
  timelineSourceLabel,
} from '../src/utils/timelineZh.ts'

function fail(message: string): never {
  throw new Error(message)
}

if (timelineHealthLabel('up') !== '可用') fail('up')
if (timelineHealthLabel('down') !== '不可用') fail('down')
if (timelineHealthLabel('unknown', 'checked') !== '已探测') fail('checked')

if (timelineSourceLabel('listing_times') !== '开盘时间表') fail('listing_times')
if (timelineSourceLabel('x_post') !== '官推') fail('x_post')
if (timelineSourceLabel('js:https://example.com/app.js') !== '官网JS') fail(`js source ${timelineSourceLabel('js:https://example.com/app.js')}`)

const gate = localizeTimelineText('ca_gate: ERC20 verified: BONER dec=18')
if (!gate.includes('已确认 ERC20') || /ca_gate|verified/i.test(gate)) fail(`gate ${gate}`)
if (localizeTimelineText('SITE_CHANGE') !== '站点变更') fail('SITE_CHANGE')
if (!localizeTimelineText('alert_ok=true').includes('允许提醒')) fail('alert_ok')
if (localizeTimelineText('low-confidence') !== '低置信') fail('low-confidence')
if (localizeTimelineText('status=即将启动; listing=未开盘') !== '状态 即将启动；开盘 未开盘') {
  fail(localizeTimelineText('status=即将启动; listing=未开盘'))
}

const note = '【非地址·非CA】 ; ca_gate: hex string (hash / git SHA), not a Solana address'
const zh = localizeTimelineText(note)
if (/ca_gate|hex string/i.test(zh)) fail(`note stayed english ${zh}`)
if (localizeMachineNote(note) === note) fail('machine note helper should translate this fixture')

if (localizeProbeError('curl: (28) Connection timed out after 25002 milliseconds') !== '连接超时') fail('timeout')
if (localizeProbeError('curl: (6) Could not resolve host: example') !== '无法解析域名') fail('dns')
if (localizeProbeError('http 404') !== 'HTTP 404 未找到') fail('404')
if (!localizeProbeError('SSL: no alternative certificate subject name matches').includes('证书')) fail('ssl')

const footer = localizeEventsNote('监控事件按 handle 归到项目时间线。由 latest + listing_scan + watchlist + ca_finds + listing_times 汇总。sample 已剔除。')
if (/\bhandle\b|\blatest\b|\blisting_scan\b|\bwatchlist\b|\bca_finds\b|\blisting_times\b|\bsample\b/i.test(footer)) {
  fail(`footer ${footer}`)
}

console.log('timeline zh checks ok')
