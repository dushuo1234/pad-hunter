import { readFileSync } from 'node:fs'
import {
  countdownLabel,
  hoursToLaunchLabel,
  playbookGroups,
  readTodayProjects,
  todayProjectsToShow,
  todayTimeView,
} from '../src/utils/todayProjects.ts'

function fail(message: string): never {
  throw new Error(message)
}

const fixture = JSON.parse(readFileSync(new URL('./fixtures/today_projects.json', import.meta.url), 'utf8'))
const now = new Date('2026-10-28T14:30:00+08:00')
const doc = readTodayProjects(fixture)

if (doc.count !== 3) fail(`count ${doc.count}`)
if (doc.timezone !== 'Asia/Shanghai') fail('timezone')
if (doc.items.map((item) => item.handle).join(',') !== 'SoonPad,bStonkAgents,NoClock') {
  fail(`sort ${doc.items.map((item) => item.handle).join(',')}`)
}
if (doc.items[1]?.handle !== 'bStonkAgents' || doc.items[1].name !== 'Stonk Agents') fail('handle strip')
if (doc.items[1].site !== 'https://stonk.example') fail('site')
if (doc.items[0]?.site) fail('javascript site must be dropped')
if (doc.items[1].playbook?.玩法.join('|') !== '质押拿积分') fail('玩法')
if (doc.items[1].playbook?.参与需求.join('|') !== '关注 X') fail('参与需求')
if (doc.items[1].playbook?.步骤.join('|') !== '打开官网|连接钱包') fail('步骤')
if (doc.items[1].playbook?.风险注意.join('|') !== '合约未审计') fail('风险注意')
if (doc.items[1].playbook?.来源[0]?.label !== '官网') fail('来源')
if (playbookGroups(doc.items[0]?.playbook).some((group) => group.label === '参与需求')) fail('empty 参与需求 shown')

const soon = todayTimeView(doc.items[0]!, now)
const stonk = todayTimeView(doc.items[1]!, now)
const plain = todayTimeView(doc.items[2]!, now)
if (!soon || soon.kind !== 'countdown' || soon.primary !== '3小时30分' || soon.secondary !== '10月28日 18:00') {
  fail(`soon clock ${JSON.stringify(soon)}`)
}
if (!stonk || stonk.primary !== '8小时30分' || stonk.primary.includes('8.5')) fail(`stonk clock must use listing_at ${stonk?.primary}`)
if (!plain || plain.kind !== 'display' || plain.primary !== '今晚' || plain.dateTime) {
  fail(`display-only clock invented a time ${JSON.stringify(plain)}`)
}
if (countdownLabel('not-a-time', now) !== null) fail('bad listing_at became a countdown')
if (countdownLabel('2026-10-28T14:30:00+08:00', now) !== '已到点') fail('due now')
if (hoursToLaunchLabel(8.5) !== '8.5 小时') fail('hours label')
if (todayTimeView({ handle: 'h', name: 'H', chain: '', hours_to_launch: 8.5 }, now)?.kind !== 'hours') fail('hours fallback')

const hidden = todayProjectsToShow(readTodayProjects({ count: 0, items: fixture.items }))
if (hidden.length !== 0) fail('count 0 must hide')
if (todayProjectsToShow(readTodayProjects(null)).length !== 0) fail('missing file must hide')
if (todayProjectsToShow(readTodayProjects({ items: [] })).length !== 0) fail('empty items must hide')
const dropped = readTodayProjects({ count: 1, items: [{ chain: 'ETH' }, { handle: 'Ok', name: 'Ok', listing_at: '2026-10-29T01:00:00+08:00' }] })
if (dropped.items.length !== 1 || dropped.items[0]?.handle !== 'Ok') fail('blank row kept')

const section = readFileSync(new URL('../src/components/TodayProjectsSection.tsx', import.meta.url), 'utf8')
const util = readFileSync(new URL('../src/utils/todayProjects.ts', import.meta.url), 'utf8')
for (const label of ['今日项目清单', '官网', 'todayProjectsToShow', 'group.label']) {
  if (!section.includes(label)) fail(`section missing ${label}`)
}
for (const label of ['玩法', '参与需求', '步骤', '风险注意']) {
  if (!util.includes(`'${label}'`) || !section.includes(label === '参与需求' ? 'group.label' : label)) {
    fail(`playbook label ${label} not wired`)
  }
}
const pad = readFileSync(new URL('../src/hooks/usePadData.ts', import.meta.url), 'utf8')
if (!pad.includes('data/today_projects.json') || !pad.includes('fetchTodayProjects()')) fail('today projects not polled with the board')
const home = readFileSync(new URL('../src/pages/HomePage.tsx', import.meta.url), 'utf8')
const workbench = readFileSync(new URL('../src/pages/WorkbenchPage.tsx', import.meta.url), 'utf8')
if (!home.includes('<TodayProjectsSection') || !workbench.includes('<TodayProjectsSection')) fail('section not mounted')

console.log(`today projects checks ok (${doc.items.length} fixture rows)`)
