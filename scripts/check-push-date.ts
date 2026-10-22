import { formatPushDate, pushDateText, resolvePushDate, withProjectPushDates } from '../src/utils/pushDate.ts'

function fail(message: string): never {
  throw new Error(message)
}

const earliest = resolvePushDate([
  {
    push_date: '2026-10-22T13:14:21+00:00',
    date_iso: '2026-10-20T01:00:00Z',
    listing_at: '2026-10-01T00:00:00+08:00',
    fetched_at: '2026-10-19T00:00:00Z',
    last_checked: '2026-10-18T00:00:00Z',
  },
])
if (!earliest || earliest.field !== 'date_iso') fail(`expected date_iso, got ${earliest?.field}`)
if (formatPushDate(earliest) !== '2026-10-20 09:00') fail(`shanghai format ${formatPushDate(earliest)}`)

const dedicated = resolvePushDate([
  { pushDate: '2026-10-21T00:00:00+08:00', date_iso: '2026-10-22T00:00:00Z' },
])
if (!dedicated || dedicated.field !== 'push_date') fail(`expected push_date, got ${dedicated?.field}`)
if (formatPushDate(dedicated) !== '2026-10-21 00:00') fail(`push_date format ${formatPushDate(dedicated)}`)

const dateOnly = resolvePushDate([{ first_seen: '2026-10-19' }])
if (!dateOnly?.dateOnly || formatPushDate(dateOnly) !== '2026-10-19') fail('date-only first_seen')

const across = resolvePushDate([
  { date_iso: '2026-10-22T13:14:21+00:00' },
  { added_at: '2026-10-16T13:31:54+00:00' },
])
if (!across || across.field !== 'added_at') fail(`expected added_at across records, got ${across?.field}`)

if (pushDateText([{ listing_at: '2026-10-27T21:00:00+08:00', notes: 'restored 2026-10-21T14:57:09+08:00' }]) !== '未知') {
  fail('listing time and notes must not become 推送日期')
}
if (pushDateText([null, undefined, {}]) !== '未知') fail('empty record')

const filled = withProjectPushDates(
  [{ handle: 'TheTimeCard', name: 'Timecard', listing_at: '2026-10-27T21:00:00+08:00' }],
  [{ twitter_handle: 'thetimecard', date_iso: '2026-10-19T22:18:40+00:00', fetched_at: '2026-10-19T15:52:39Z' }],
)
const filledStamp = resolvePushDate(filled)
if (!filledStamp || filledStamp.field !== 'push_date') fail('snapshot date should land on push_date')
if (formatPushDate(filledStamp) !== '2026-10-20 06:18') fail(`snapshot shanghai ${formatPushDate(filledStamp)}`)
if ('date_iso' in filled[0]) fail('snapshot fill must not write date_iso')
if (filled[0].listing_at !== '2026-10-27T21:00:00+08:00') fail('snapshot fill must not rewrite listing_at')

const kept = withProjectPushDates(
  [{ handle: 'alpha', date_iso: '2026-10-22T13:14:21+00:00' }],
  [{ handle: 'alpha', date_iso: '2026-10-01T00:00:00Z' }],
)
if (resolvePushDate(kept)?.field !== 'date_iso') fail('existing candidate timestamp wins over an older snapshot when both exist')
if (kept[0].date_iso !== '2026-10-22T13:14:21+00:00') fail('candidate date_iso changed')

console.log('push date checks ok')
