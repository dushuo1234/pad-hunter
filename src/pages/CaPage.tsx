import { useMemo, useState } from 'react'
import { PinWorkbenchButton } from '../components/PinWorkbenchButton'
import { PushDate } from '../components/PushDate'
import { ReviewedMark } from '../components/ReviewedMark'
import { useCaFinds } from '../hooks/useCaFinds'
import { monitorPath } from '../router'
import type { CaFind, CaProjectLock, CaStatus, Candidate } from '../types'
import {
  CA_ROLE_ZH,
  caAddressId,
  caFindKey,
  caSourceBadges,
  chainOptions,
  compareFindsByNewest,
  displayProjectName,
  explorerFor,
  findIsLaunched,
  groupCaFinds,
  indexLaunchedProjects,
  lockForFind,
  lockIsLaunched,
  safeEvidenceUrl,
  sameProject,
  sharesLock,
  type CaProjectGroup,
} from '../utils/caFinds'
import { localizeMachineNote } from '../utils/caNoteZh'
import { findByHandle } from '../utils/candidates'
import { formatShanghai, shortAddr, xProfileUrl } from '../utils/format'
import { reviewSnapshot } from '../utils/reviewed'
import type { LaunchedItem } from '../utils/launched'

interface CaPageProps {
  candidates: Candidate[]
  launchedItems: LaunchedItem[]
}

type Focus = 'all' | 'confirmed' | 'candidate' | 'superseded' | 'not_ca' | 'copycat' | 'launched'
type RowTone = 'confirmed' | 'candidate' | 'superseded' | 'copycat' | 'quiet' | 'activity'

const FIELD =
  'h-10 w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]'

export function CaPage({ candidates, launchedItems }: CaPageProps) {
  const {
    finds,
    suspectedCopycats,
    supersededArchive,
    launchedHistory,
    walletActivity,
    locks,
    generatedAt,
    statusCounts,
    suspectedCopycatCount,
    confidenceModel,
    lastChecked,
    loading,
    error,
    freshKeys,
  } = useCaFinds()
  const [search, setSearch] = useState('')
  const [chain, setChain] = useState('')
  const [focus, setFocus] = useState<Focus>('all')

  const pool = useMemo(
    () => [...finds, ...suspectedCopycats, ...supersededArchive, ...launchedHistory, ...walletActivity],
    [finds, suspectedCopycats, supersededArchive, launchedHistory, walletActivity],
  )
  const launchIndex = useMemo(() => indexLaunchedProjects(launchedItems), [launchedItems])
  const isLaunched = useMemo(() => (find: CaFind) => findIsLaunched(find, launchIndex), [launchIndex])
  const chains = useMemo(() => chainOptions(pool), [pool])
  const match = useMemo(() => {
    const query = search.trim().toLowerCase().replace(/^@/, '')
    return (find: CaFind) => {
      if (chain && find.chain !== chain) return false
      if (!query) return true
      const hay = `${find.project} ${find.handle} ${find.address} ${find.labelZh} ${localizeMachineNote(find.labelZh)} ${find.creator} ${find.note} ${localizeMachineNote(find.note)} ${find.confirmBasisZh} ${localizeMachineNote(find.confirmBasisZh)}`.toLowerCase()
      return hay.includes(query)
    }
  }, [search, chain])

  const confirmed = useMemo(
    () => finds.filter((find) => find.caStatus === 'confirmed' && !isLaunched(find) && match(find)).sort(compareFindsByNewest),
    [finds, isLaunched, match],
  )
  const pending = useMemo(
    () => finds.filter((find) => find.caStatus === 'candidate' && !isLaunched(find) && match(find)).sort(compareFindsByNewest),
    [finds, isLaunched, match],
  )
  const notCa = useMemo(
    () =>
      finds
        .filter((find) => find.caStatus !== 'confirmed' && find.caStatus !== 'candidate' && !isLaunched(find) && match(find))
        .sort(compareFindsByNewest),
    [finds, isLaunched, match],
  )
  const superseded = useMemo(
    () => supersededArchive.filter((find) => !isLaunched(find) && match(find)).sort(compareFindsByNewest),
    [supersededArchive, isLaunched, match],
  )
  const copycats = useMemo(
    () => suspectedCopycats.filter((find) => !isLaunched(find) && match(find)).sort(compareFindsByNewest),
    [suspectedCopycats, isLaunched, match],
  )
  const activity = useMemo(
    () => walletActivity.filter((find) => !isLaunched(find) && match(find)).sort(compareFindsByNewest),
    [walletActivity, isLaunched, match],
  )
  const activeLocks = useMemo(() => locks.filter((lock) => !lockIsLaunched(lock, launchIndex)), [locks, launchIndex])
  const confirmedGroups = useMemo(() => groupCaFinds(confirmed), [confirmed])
  const lonelyActiveLocks = useMemo(
    () => activeLocks.filter((lock) => !confirmed.some((find) => lockForFind([lock], find))),
    [activeLocks, confirmed],
  )
  const showConfirmed = confirmedGroups.length > 0 || lonelyActiveLocks.length > 0 || focus === 'confirmed'
  const launchedRows = useMemo(() => {
    const ranked = [...finds, ...suspectedCopycats, ...supersededArchive, ...launchedHistory, ...walletActivity]
      .filter((find) => isLaunched(find) && match(find) && launchedMatchesFocus(find, focus))
      .sort(compareFindsByNewest)
    const seen = new Set<string>()
    const rows: CaFind[] = []
    for (const find of ranked) {
      const key = `${find.caStatus}|${find.activity ? 1 : 0}|${find.chain.toLowerCase()}|${caAddressId(find.address)}`
      if (seen.has(key)) continue
      seen.add(key)
      rows.push(find)
    }
    return rows
  }, [finds, suspectedCopycats, supersededArchive, launchedHistory, walletActivity, isLaunched, match, focus])
  const launchedGroups = useMemo(() => groupCaFinds(launchedRows), [launchedRows])
  const launchedCount = useMemo(() => {
    const seen = new Set<string>()
    let count = 0
    for (const find of [...finds, ...suspectedCopycats, ...supersededArchive, ...launchedHistory, ...walletActivity]) {
      if (!isLaunched(find)) continue
      const key = `${find.caStatus}|${find.activity ? 1 : 0}|${find.chain.toLowerCase()}|${caAddressId(find.address)}`
      if (seen.has(key)) continue
      seen.add(key)
      count += 1
    }
    return count
  }, [finds, suspectedCopycats, supersededArchive, launchedHistory, walletActivity, isLaunched])
  const freshAlerts = useMemo(
    () => finds.filter((find) => find.caStatus === 'confirmed' && find.alertOk && freshKeys.has(caFindKey(find))).length,
    [finds, freshKeys],
  )

  const checkedLabel = lastChecked ? formatShanghai(lastChecked, true) : ''
  const generatedLabel = generatedAt ? formatShanghai(generatedAt, true) : ''
  const show = (id: Focus) => focus === 'all' || focus === id
  const filtering = Boolean(search.trim() || chain)

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">合约发现</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">发现CA</h1>
        <p className="font-mono text-[11px] text-[var(--color-ink-muted)]" title="Asia/Shanghai">
          {checkedLabel ? `上次检查 ${checkedLabel} 北京时间` : '正在检查…'}
          {generatedLabel ? ` · 数据 ${generatedLabel}` : ''}
        </p>
      </div>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        已确认 CA 只认两条路：监控钱包经已知工厂创建，和/或官推贴出地址并链上核验为代币或 TapeOut 晶体管 / Processor。同名合约是疑似山寨，不会响铃。官推锁定之后，后来的非官方 CA 不再推送；监控钱包的相关地址动态照常显示。
      </p>
      {confidenceModel && (
        <p
          className="mt-2 max-w-3xl font-mono text-[11px] leading-relaxed text-[var(--color-ink-muted)]"
          title="已确认要同时满足核验通过，以及监控钱包创建或官推确认。只对上名字的是疑似山寨。监控钱包创建过、但官推指定了别的地址，算非正式。只从站点扫到的是待确认。"
        >
          计数来自 status_counts。高 / 中 / 低置信仍写在每行上，但不决定是不是确认 CA。
        </p>
      )}

      {loading && finds.length === 0 && suspectedCopycats.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          正在读取合约发现…
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)]">
            <label className="flex flex-col gap-1.5" htmlFor="ca-search">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">搜索</span>
              <input
                id="ca-search"
                type="search"
                placeholder="项目 / 合约地址"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                className={FIELD}
              />
            </label>
            <label className="flex flex-col gap-1.5" htmlFor="ca-chain">
              <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">链</span>
              <select id="ca-chain" value={chain} onChange={(event) => setChain(event.target.value)} className={FIELD}>
                <option value="">全部链</option>
                {chains.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="CA 状态">
            <StatusChip id="all" label="全部" count={null} active={focus === 'all'} onSelect={setFocus} />
            <StatusChip id="confirmed" label="已确认CA" count={statusCounts.confirmed} active={focus === 'confirmed'} onSelect={setFocus} />
            <StatusChip id="candidate" label="待确认" count={statusCounts.candidate} active={focus === 'candidate'} onSelect={setFocus} />
            <StatusChip
              id="superseded"
              label="非正式·官推未认"
              count={statusCounts.superseded}
              active={focus === 'superseded'}
              onSelect={setFocus}
            />
            <StatusChip id="not_ca" label="非CA" count={statusCounts.not_ca} active={focus === 'not_ca'} onSelect={setFocus} />
            <StatusChip
              id="copycat"
              label="疑似山寨"
              count={suspectedCopycatCount}
              active={focus === 'copycat'}
              onSelect={setFocus}
            />
            <StatusChip id="launched" label="已开盘" count={launchedCount} active={focus === 'launched'} onSelect={setFocus} />
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-[var(--color-ink-muted)]">
            <span>
              已确认 {statusCounts.confirmed} · 待确认 {statusCounts.candidate} · 非正式 {statusCounts.superseded} · 非CA {statusCounts.not_ca} · 疑似山寨 {suspectedCopycatCount}
            </span>
            {freshAlerts > 0 && (
              <span className="text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]" aria-live="polite">
                本次打开后新增确认 {freshAlerts} 条
              </span>
            )}
            {filtering && <span>下面是筛选结果</span>}
            {error && <span className="text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]">{error}</span>}
          </div>

          {show('confirmed') && showConfirmed && (
            <section className="mt-6" aria-labelledby="confirmed-heading">
              <h2 id="confirmed-heading" className="text-lg font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
                已确认 CA
              </h2>
              <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[var(--color-ink-muted)]">
                徽章是 ca_status_zh，旁边是确认路径。只有 alert_ok 的行会响铃、标成「新」。
              </p>
              {confirmedGroups.length === 0 ? (
                focus === 'confirmed' ? (
                  <p className="mt-3 rounded-2xl border border-dashed border-[var(--color-line)] px-4 py-8 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
                    当前筛选下没有未开盘项目的已确认 CA。
                  </p>
                ) : null
              ) : (
                <div className="mt-3 flex flex-col gap-4">
                  {confirmedGroups.map((group) => (
                    <ProjectGroup
                      key={group.key}
                      group={group}
                      candidates={candidates}
                      freshKeys={freshKeys}
                      locks={locks}
                      activity={activity.filter((row) => group.finds.some((find) => sameProject(row, find) || sharesLock(locks, row, find)))}
                    />
                  ))}
                </div>
              )}
              <LockedActivity
                locks={activeLocks}
                confirmed={confirmed}
                activity={activity}
                candidates={candidates}
                freshKeys={freshKeys}
              />
            </section>
          )}

          {show('candidate') && (pending.length > 0 || focus === 'candidate') && (
            <section className="mt-8" aria-labelledby="candidate-heading">
              <h2 id="candidate-heading" className="text-lg font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
                待确认
              </h2>
              <p className="mt-1 text-xs text-[var(--color-ink-muted)]">站点扫到的地址，还没有钱包工厂或官推证明。不会当确认 CA 推送。</p>
              {pending.length === 0 ? (
                <p className="mt-3 text-sm text-[var(--color-ink-muted)]">没有待确认行。</p>
              ) : (
                <ul className="mt-3 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
                  {pending.map((find) => (
                    <FindRow key={caFindKey(find)} find={find} fresh={false} candidates={candidates} tone="candidate" locks={locks} />
                  ))}
                </ul>
              )}
            </section>
          )}

          {show('superseded') && (superseded.length > 0 || focus === 'superseded') && (
            <section className="mt-8" aria-labelledby="superseded-heading">
              <h2 id="superseded-heading" className="text-lg font-bold text-[var(--color-ink-muted)]">非正式·官推未认</h2>
              <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[var(--color-ink-muted)]">
                活跃列表里的计数是 {statusCounts.superseded}。监控钱包创建过、但官推后来指定了别的地址，这些行变灰，并链到 superseded_by。不会推送。
              </p>
              {superseded.length === 0 ? (
                <p className="mt-3 text-sm text-[var(--color-ink-muted)]">没有已被取代的行。</p>
              ) : (
                <ul className="mt-3 overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-cream-2)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)]">
                  {superseded.map((find) => (
                    <FindRow key={caFindKey(find)} find={find} fresh={false} candidates={candidates} tone="superseded" locks={locks} />
                  ))}
                </ul>
              )}
            </section>
          )}

          {show('copycat') && (
            <CopycatSection
              rows={copycats}
              open={focus === 'copycat' || filtering}
              candidates={candidates}
              locks={locks}
              freshKeys={freshKeys}
            />
          )}

          {show('not_ca') && (
            <QuietSection
              title="非CA"
              summary={`扫出钱包、NFT 合约、非地址 · ${notCa.length} 条`}
              note="这些不是代币 CA。扫出钱包不会出现在确认列表里，NFT 也不会按代币 CA 推送。"
              open={focus === 'not_ca' || filtering}
              rows={notCa}
              candidates={candidates}
              locks={locks}
            />
          )}

          {show('confirmed') && <OrphanActivity activity={activity} confirmed={confirmed} candidates={candidates} freshKeys={freshKeys} locks={activeLocks} />}

          {(show('launched') || launchedGroups.length > 0) && (
            <LaunchedArchive groups={launchedGroups} candidates={candidates} freshKeys={freshKeys} locks={locks} />
          )}
        </>
      )}
    </main>
  )
}

function launchedMatchesFocus(find: CaFind, focus: Focus): boolean {
  if (focus === 'all' || focus === 'launched') return true
  if (find.activity) return false
  if (focus === 'confirmed') return find.caStatus === 'confirmed'
  if (focus === 'candidate') return find.caStatus === 'candidate'
  if (focus === 'superseded') return find.caStatus === 'superseded'
  if (focus === 'copycat') return find.caStatus === 'suspected_copycat'
  return find.caStatus !== 'confirmed' && find.caStatus !== 'candidate' && find.caStatus !== 'superseded' && find.caStatus !== 'suspected_copycat'
}

function toneForFind(find: CaFind): RowTone {
  if (find.activity) return 'activity'
  if (find.caStatus === 'confirmed') return 'confirmed'
  if (find.caStatus === 'candidate') return 'candidate'
  if (find.caStatus === 'superseded') return 'superseded'
  if (find.caStatus === 'suspected_copycat') return 'copycat'
  return 'quiet'
}

function StatusChip({
  id,
  label,
  count,
  active,
  onSelect,
}: {
  id: Focus
  label: string
  count: number | null
  active: boolean
  onSelect: (id: Focus) => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={() => onSelect(id)}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
        active
          ? 'bg-[var(--color-ink)] text-white dark:bg-[var(--color-night-ink)] dark:text-[var(--color-night)]'
          : 'border border-[var(--color-line)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]'
      }`}
    >
      {label}
      {count != null && (
        <span className={`font-mono text-[10px] ${active ? 'text-white/80 dark:text-black/70' : 'text-[var(--color-ink-muted)]'}`}>{count}</span>
      )}
    </button>
  )
}

function ProjectGroup({
  group,
  candidates,
  freshKeys,
  locks,
  activity,
}: {
  group: CaProjectGroup
  candidates: Candidate[]
  freshKeys: Set<string>
  locks: CaProjectLock[]
  activity: CaFind[]
}) {
  const sample = group.finds[0]
  const name = displayProjectName(group.project, group.handle)
  const lock = sample ? lockForFind(locks, sample) : null
  const catalog = group.handle ? findByHandle(candidates, group.handle) : undefined
  return (
    <section className="overflow-hidden rounded-2xl border border-[#166534]/30 bg-[var(--color-card)] dark:border-[#86efac]/30 dark:bg-[var(--color-night-card)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-line)] px-4 py-3 dark:border-[var(--color-night-line)]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <ProjectTitle name={name} handle={group.handle} />
            <ReviewedMark
              handle={group.handle || catalog?.handle}
              name={name}
              snapshot={reviewSnapshot({
                listing_at: catalog?.listing_at,
                launch_at: catalog?.launch_at,
                status: catalog?.status,
                listing: catalog?.listing,
                ca: sample?.address || catalog?.ca,
              })}
            />
            <span className="font-mono text-[10px] text-[var(--color-ink-muted)]">{group.finds.length} 个已确认</span>
            {lock && <LockBadge url={lock.url || sample?.lockUrl || ''} at={sample?.lockAt} />}
            <PushDate records={catalogMatch(candidates, group.handle)} />
          </div>
          {group.handle && <HandleLink handle={group.handle} />}
        </div>
        {group.handle && (
          <a href={monitorPath(group.handle)} className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline">
            监控详情
          </a>
        )}
      </header>
      <ul>
        {group.finds.map((find) => (
          <FindRow
            key={caFindKey(find)}
            find={find}
            fresh={find.alertOk && freshKeys.has(caFindKey(find))}
            candidates={candidates}
            tone="confirmed"
            locks={locks}
          />
        ))}
      </ul>
      <ActivityBlock rows={activity} locked={Boolean(lock)} freshKeys={freshKeys} candidates={candidates} locks={locks} />
    </section>
  )
}

function LockedActivity({
  locks,
  confirmed,
  activity,
  candidates,
  freshKeys,
}: {
  locks: CaProjectLock[]
  confirmed: CaFind[]
  activity: CaFind[]
  candidates: Candidate[]
  freshKeys: Set<string>
}) {
  const lonely = locks.filter((lock) => !confirmed.some((find) => lockForFind([lock], find)))
  if (lonely.length === 0) return null
  return (
    <div className="mt-4 flex flex-col gap-4">
      {lonely.map((lock) => {
        const rows = activity.filter((row) => lockForFind([lock], row))
        const name = displayProjectName(lock.project, lock.handle) 
        return (
          <section key={lock.id} className="overflow-hidden rounded-2xl border border-[#1d4ed8]/30 bg-[var(--color-card)] dark:border-[#93c5fd]/30 dark:bg-[var(--color-night-card)]">
            <header className="flex flex-wrap items-center gap-2 px-4 py-3">
              <h3 className="text-sm font-semibold">{name === '未命名项目' ? '已锁定项目' : name}</h3>
              <LockBadge url={lock.url} />
              <PushDate records={catalogMatch(candidates, lock.handle)} />
            </header>
            <ActivityBlock rows={rows} locked freshKeys={freshKeys} candidates={candidates} locks={[lock]} />
          </section>
        )
      })}
    </div>
  )
}

function OrphanActivity({
  activity,
  confirmed,
  candidates,
  freshKeys,
  locks,
}: {
  activity: CaFind[]
  confirmed: CaFind[]
  candidates: Candidate[]
  freshKeys: Set<string>
  locks: CaProjectLock[]
}) {
  const rows = activity.filter(
    (row) => !confirmed.some((find) => sameProject(row, find) || sharesLock(locks, row, find)) && !lockForFind(locks, row),
  )
  if (rows.length === 0) return null
  return (
    <section className="mt-6">
      <h2 className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">监控钱包动态</h2>
      <ActivityBlock rows={rows} locked={false} freshKeys={freshKeys} candidates={candidates} locks={locks} />
    </section>
  )
}

function ActivityBlock({
  rows,
  locked,
  freshKeys,
  candidates,
  locks,
}: {
  rows: CaFind[]
  locked: boolean
  freshKeys: Set<string>
  candidates: Candidate[]
  locks: CaProjectLock[]
}) {
  if (rows.length === 0 && !locked) return null
  return (
    <div className="border-t border-dashed border-[var(--color-line)] bg-[var(--color-cream)] px-4 py-3 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night)]">
      <p className="text-xs font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">监控钱包动态</p>
      <p className="mt-1 text-[11px] leading-relaxed text-[var(--color-ink-muted)]">
        {locked
          ? '官推已锁定，后来的非官方 CA 不再推送。这里仍显示监控钱包的相关地址，不当作新 CA，也不响铃。'
          : '相关地址动态，不是确认 CA，不响铃。'}
      </p>
      {rows.length === 0 ? (
        <p className="mt-2 text-[11px] text-[var(--color-ink-muted)]">还没有新的钱包动态。</p>
      ) : (
        <ul className="mt-2">
          {rows.map((find) => (
            <FindRow
              key={caFindKey(find)}
              find={find}
              fresh={freshKeys.has(caFindKey(find))}
              candidates={candidates}
              tone="activity"
              locks={locks}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

function CopycatSection({
  rows,
  open,
  candidates,
  locks,
  freshKeys,
}: {
  rows: CaFind[]
  open: boolean
  candidates: Candidate[]
  locks: CaProjectLock[]
  freshKeys: Set<string>
}) {
  return (
    <details
      key={open ? 'copycat-open' : 'copycat-shut'}
      open={open}
      className="mt-8 rounded-2xl border border-dashed border-[#9f1239] bg-[#fff1f2] px-4 py-3 dark:border-[#fb7185] dark:bg-[#4c0519]"
    >
      <summary className="cursor-pointer list-none text-sm font-bold text-[#9f1239] dark:text-[#fecdd3]">
        疑似山寨 · {rows.length} 条
        <span className="ml-2 font-normal text-[11px] text-[#9f1239]/80 dark:text-[#fecdd3]/80">名字或符号对上而已，不是确认 CA，不会响铃</span>
      </summary>
      <p className="mt-2 text-xs leading-relaxed text-[#881337] dark:text-[#fecdd3]">
        创建者不在监控钱包里，官推也还没认。不要跟。和上面的已确认列表分开。
      </p>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-[#9f1239] dark:text-[#fecdd3]">没有疑似山寨。</p>
      ) : (
        <ul className="mt-3 overflow-hidden rounded-xl border border-[#fecdd3] bg-white dark:border-[#fb7185]/40 dark:bg-[var(--color-night-card)]">
          {rows.map((find) => (
            <FindRow
              key={caFindKey(find)}
              find={find}
              fresh={freshKeys.has(caFindKey(find))}
              candidates={candidates}
              tone="copycat"
              locks={locks}
            />
          ))}
        </ul>
      )}
    </details>
  )
}

function QuietSection({
  title,
  summary,
  note,
  open,
  rows,
  candidates,
  locks,
}: {
  title: string
  summary: string
  note: string
  open: boolean
  rows: CaFind[]
  candidates: Candidate[]
  locks: CaProjectLock[]
}) {
  return (
    <details
      key={open ? `${title}-open` : `${title}-shut`}
      open={open}
      className="mt-6 rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] px-4 py-3 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]"
    >
      <summary className="cursor-pointer list-none text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
        {title}
        <span className="ml-2 font-normal text-[11px] text-[var(--color-ink-muted)]">{summary}</span>
      </summary>
      <p className="mt-2 text-xs text-[var(--color-ink-muted)]">{note}</p>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-[var(--color-ink-muted)]">没有这类地址。</p>
      ) : (
        <ul className="mt-3">
          {rows.map((find) => (
            <FindRow key={caFindKey(find)} find={find} fresh={false} candidates={candidates} tone="quiet" locks={locks} />
          ))}
        </ul>
      )}
    </details>
  )
}

function FindRow({
  find,
  fresh,
  candidates,
  tone,
  locks,
}: {
  find: CaFind
  fresh: boolean
  candidates: Candidate[]
  tone: 'confirmed' | 'candidate' | 'superseded' | 'copycat' | 'quiet' | 'activity'
  locks: CaProjectLock[]
}) {
  const explorer = explorerFor(find.chain, find.address)
  const evidence = safeEvidenceUrl(find.evidence_url)
  const tweet = safeEvidenceUrl(find.officialXUrl)
  const lock = lockForFind(locks, find)
  const lockUrl = safeEvidenceUrl(find.lockUrl || lock?.url || '')
  const when = formatShanghai(find.detected_at, true)
  const name = displayProjectName(find.project, find.handle)
  const candidate = find.handle ? findByHandle(candidates, find.handle) : undefined
  const showPair = Boolean(find.pairedWith) && (find.caRole === 'processor' || tone !== 'copycat')
  const grey = tone === 'superseded'
  const highlight = fresh && find.alertOk && tone === 'confirmed'
  const note = localizeMachineNote(find.note)
  const basis = localizeMachineNote(find.confirmBasisZh)
  const label = localizeMachineNote(find.labelZh)
  return (
    <li
      id={`ca-${find.address.toLowerCase()}`}
      className={`border-b border-[var(--color-line)] px-4 py-3 last:border-b-0 dark:border-[var(--color-night-line)] ${
        highlight ? 'ca-row-new' : ''
      } ${grey ? 'text-[var(--color-ink-muted)]' : ''}`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {highlight && <span className="rounded-md bg-[var(--color-orange)] px-1.5 py-0.5 text-[10px] font-semibold text-white">新</span>}
        {fresh && tone === 'activity' && (
          <span className="rounded-md bg-[var(--color-cream-2)] px-1.5 py-0.5 text-[10px] text-[var(--color-ink-muted)] dark:bg-[var(--color-night-2)]">新动态</span>
        )}
        {fresh && tone === 'copycat' && (
          <span className="rounded-md border border-dashed border-[#9f1239] px-1.5 py-0.5 text-[10px] text-[#9f1239] dark:border-[#fecdd3] dark:text-[#fecdd3]">
            刚扫到
          </span>
        )}
        <StatusBadge status={find.caStatus} text={find.caStatusZh || (tone === 'activity' ? '钱包动态' : '未标注')} />
        {tone !== 'confirmed' && (
          <ReviewedMark
            handle={find.handle || candidate?.handle}
            name={name}
            snapshot={reviewSnapshot({
              listing_at: candidate?.listing_at,
              launch_at: candidate?.launch_at,
              status: candidate?.status,
              listing: candidate?.listing,
              ca: find.address || candidate?.ca,
            })}
          />
        )}
        {find.provenanceZh && tone !== 'quiet' && tone !== 'activity' && <ProvenanceChip text={find.provenanceZh} />}
        {find.caRole && CA_ROLE_ZH[find.caRole] && <MetaChip>{CA_ROLE_ZH[find.caRole]}</MetaChip>}
        {(find.caLocked || lock) && tone !== 'quiet' && <LockBadge url={lockUrl || ''} at={find.lockAt} />}
        {find.confidence && <MetaChip>{confidenceLabel(find.confidence)}</MetaChip>}
        <SourceBadges find={find} />
        {find.chain && <MetaChip>{find.chain}</MetaChip>}
        {label && <MetaChip>{label}</MetaChip>}
        {when && (
          <time className="font-mono text-[11px] text-[var(--color-ink-muted)]" dateTime={find.detected_at}>
            {when} 北京时间
          </time>
        )}
        <PushDate records={candidate ? [candidate] : []} />
      </div>
      {tone !== 'confirmed' && (
        <p className="mt-2 text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{name}</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <code
          className={`min-w-0 break-all font-mono text-[13px] ${grey ? 'text-[var(--color-ink-muted)]' : 'text-[var(--color-ink)] dark:text-[var(--color-night-ink)]'}`}
        >
          {find.address}
        </code>
        <CopyButton text={find.address} />
        {explorer && (
          <a href={explorer.url} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-[var(--color-orange)] hover:underline">
            {explorer.label}
          </a>
        )}
      </div>
      {basis && <p className="mt-2 text-xs leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">{basis}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        {tweet && (
          <a href={tweet} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-[var(--color-orange)] hover:underline">
            官推
          </a>
        )}
        {evidence && evidence !== tweet && (
          <a href={evidence} target="_blank" rel="noreferrer" className="max-w-full truncate font-mono text-[11px] text-[var(--color-orange)] hover:underline">
            证据 {evidence.replace(/^https?:\/\//, '')}
          </a>
        )}
        {showPair && <PairLink chain={find.chain} address={find.pairedWith} label="配对" />}
        {find.processor && find.processor.toLowerCase() !== find.address.toLowerCase() && find.caRole === 'transistors' && (
          <PairLink chain={find.chain} address={find.processor} label="配对 Processor" />
        )}
        {find.supersededBy && (
          <a
            href={`#ca-${find.supersededBy.toLowerCase()}`}
            className="font-mono text-[11px] text-[var(--color-ink-soft)] underline decoration-dotted dark:text-[var(--color-night-soft)]"
          >
            已被取代，现用 {shortAddr(find.supersededBy)}
          </a>
        )}
        {find.handle && (
          <a href={monitorPath(find.handle)} className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline">
            监控详情
          </a>
        )}
        <PinWorkbenchButton
          candidate={candidate}
          name={name}
          handle={find.handle || candidate?.handle}
          ca={tone === 'confirmed' && find.alertOk ? find.address : undefined}
          caChain={tone === 'confirmed' && find.alertOk ? find.chain : undefined}
        />
      </div>
      {(find.cpu || find.mintPriceBnb || find.supplyCap) && (
        <p className="mt-2 font-mono text-[11px] text-[var(--color-ink-muted)]">
          {[find.cpu && `CPU ${find.cpu}`, find.mintPriceBnb && `铸造 ${find.mintPriceBnb} BNB`, find.supplyCap && `上限 ${find.supplyCap}`]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}
      {find.creator && (
        <p className="mt-2 font-mono text-[11px] text-[var(--color-ink-muted)]">
          创建者 {shortAddr(find.creator)}
          {find.creatorWatched === false ? ' · 不在监控钱包' : find.creatorWatched === true ? ' · 在监控钱包' : ''}
          {find.tx ? ` · tx ${shortAddr(find.tx)}` : ''}
        </p>
      )}
      {note && (
        <p className="mt-2 text-xs leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">{note}</p>
      )}
    </li>
  )
}

function PairLink({ chain, address, label }: { chain: string; address: string; label: string }) {
  const explorer = explorerFor(chain, address)
  return (
    <span className="inline-flex items-center gap-2 font-mono text-[11px] text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
      <a href={`#ca-${address.toLowerCase()}`} className="underline decoration-dotted">
        {label} {shortAddr(address)}
      </a>
      {explorer && (
        <a href={explorer.url} target="_blank" rel="noreferrer" className="text-[var(--color-orange)] hover:underline">
          {explorer.label}
        </a>
      )}
    </span>
  )
}

function StatusBadge({ status, text }: { status: CaStatus; text: string }) {
  const tone =
    status === 'confirmed'
      ? 'border-[#166534] bg-[#ecfdf3] text-[#166534] dark:border-[#86efac] dark:bg-[#052e16] dark:text-[#86efac]'
      : status === 'suspected_copycat'
        ? 'border-[#9f1239] bg-[#ffe4e6] text-[#9f1239] dark:border-[#fecdd3] dark:bg-[#4c0519] dark:text-[#fecdd3]'
        : status === 'superseded'
          ? 'border-[var(--color-line)] bg-[var(--color-cream-2)] text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night)]'
          : status === 'candidate'
            ? 'border-[#a16207] bg-[#fefce8] text-[#854d0e] dark:border-[#fde68a] dark:bg-[#422006] dark:text-[#fde68a]'
            : 'border-[var(--color-line)] text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]'
  return <span className={`rounded-md border px-2 py-0.5 text-[11px] font-semibold ${tone}`}>{text}</span>
}

function ProvenanceChip({ text }: { text: string }) {
  return (
    <span className="rounded-md bg-[var(--color-ink)] px-2 py-0.5 text-[11px] font-medium text-white dark:bg-[var(--color-night-ink)] dark:text-[var(--color-night)]">
      {text}
    </span>
  )
}

function LockBadge({ url, at }: { url: string; at?: string }) {
  const className =
    'rounded-md border border-[#1d4ed8] bg-[#eff6ff] px-2 py-0.5 text-[11px] font-semibold text-[#1e3a8a] dark:border-[#93c5fd] dark:bg-[#172554] dark:text-[#bfdbfe]'
  const title = at ? `官推已锁定 ${at}` : '官推已锁定'
  if (!url) return <span className={className} title={title}>官推已锁定</span>
  return (
    <a href={url} target="_blank" rel="noreferrer" className={`${className} hover:underline`} title={title}>
      官推已锁定
    </a>
  )
}

function MetaChip({ children }: { children: string }) {
  return (
    <span className="rounded-md border border-[var(--color-line)] bg-[var(--color-cream-2)] px-2 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]">
      {children}
    </span>
  )
}

function SourceBadges({ find }: { find: CaFind }) {
  const badges = caSourceBadges(find.sourceRefs.length > 0 ? find.sourceRefs : find.source ? [find.source] : [], find.evidence_url)
  const className =
    'rounded-md bg-[var(--color-orange-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]'
  if (badges.length === 0) return <span className={className}>未知来源</span>
  return badges.map((badge) =>
    badge.href ? (
      <a key={badge.label} href={badge.href} target="_blank" rel="noreferrer" className={`${className} hover:underline`}>
        {badge.label}
      </a>
    ) : (
      <span key={badge.label} className={className}>
        {badge.label}
      </span>
    ),
  )
}

function LaunchedArchive({
  groups,
  candidates,
  freshKeys,
  locks,
}: {
  groups: CaProjectGroup[]
  candidates: Candidate[]
  freshKeys: Set<string>
  locks: CaProjectLock[]
}) {
  return (
    <section className="mt-10" aria-labelledby="launched-ca-heading">
      <h2 id="launched-ca-heading" className="text-lg font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
        已开盘
      </h2>
      <p className="mt-1 max-w-3xl text-xs leading-relaxed text-[var(--color-ink-muted)]">
        已经开盘的项目放在这里，不再排在未开盘发现前面。同一档里按发现时间从新到旧。状态和「新」标记跟上面一样。
      </p>
      {groups.length === 0 ? (
        <p className="mt-3 rounded-2xl border border-dashed border-[var(--color-line)] px-4 py-8 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          没有已开盘项目的 CA。
        </p>
      ) : (
        <div className="mt-3 flex flex-col gap-4">
          {groups.map((group) => {
            const sample = group.finds[0]
            const name = displayProjectName(group.project, group.handle)
            const lock = sample ? lockForFind(locks, sample) : null
            return (
              <section
                key={group.key}
                className="overflow-hidden rounded-2xl border border-dashed border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]"
              >
                <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-line)] px-4 py-3 dark:border-[var(--color-night-line)]">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <ProjectTitle name={name} handle={group.handle} />
                      <span className="rounded-md bg-[var(--color-orange-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]">
                        已开盘
                      </span>
                      <span className="font-mono text-[10px] text-[var(--color-ink-muted)]">{group.finds.length} 条</span>
                      {lock && <LockBadge url={lock.url || sample?.lockUrl || ''} at={sample?.lockAt} />}
                      <PushDate records={catalogMatch(candidates, group.handle)} />
                    </div>
                    {group.handle && <HandleLink handle={group.handle} />}
                  </div>
                  {group.handle && (
                    <a href={monitorPath(group.handle)} className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline">
                      监控详情
                    </a>
                  )}
                </header>
                <ul>
                  {group.finds.map((find) => (
                    <FindRow
                      key={caFindKey(find)}
                      find={find}
                      fresh={freshKeys.has(caFindKey(find))}
                      candidates={candidates}
                      tone={toneForFind(find)}
                      locks={locks}
                    />
                  ))}
                </ul>
              </section>
            )
          })}
        </div>
      )}
    </section>
  )
}

function catalogMatch(candidates: Candidate[], handle: string): Candidate[] {
  if (!handle) return []
  const match = findByHandle(candidates, handle)
  return match ? [match] : []
}

function ProjectTitle({ name, handle }: { name: string; handle: string }) {
  if (!handle) return <h2 className="truncate text-sm font-semibold">{name}</h2>
  return (
    <a href={monitorPath(handle)} className="truncate text-sm font-semibold hover:text-[var(--color-orange-deep)] dark:hover:text-[var(--color-orange)]">
      {name}
    </a>
  )
}

function HandleLink({ handle }: { handle: string }) {
  return (
    <a
      href={xProfileUrl(handle)}
      target="_blank"
      rel="noreferrer"
      className="mt-0.5 inline-block font-mono text-[11px] text-[var(--color-ink-muted)] hover:text-[var(--color-orange)]"
    >
      @{handle.replace(/^@/, '')}
    </a>
  )
}

function confidenceLabel(value: CaFind['confidence']): string {
  if (value === 'high') return '高置信'
  if (value === 'medium') return '中置信'
  if (value === 'low') return '低置信'
  return ''
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={() => {
        void copyText(text).then((ok) => {
          if (!ok) return
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1200)
        })
      }}
      className="rounded-md border border-[var(--color-line)] bg-[var(--color-card)] px-2 py-0.5 font-mono text-[11px] text-[var(--color-ink-soft)] transition hover:border-[var(--color-orange)] hover:text-[var(--color-orange-deep)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]"
    >
      {copied ? '已复制' : '复制'}
    </button>
  )
}

async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text)
    return true
  } catch {
    try {
      const area = document.createElement('textarea')
      area.value = text
      area.setAttribute('readonly', '')
      area.style.position = 'fixed'
      area.style.left = '-9999px'
      document.body.appendChild(area)
      area.select()
      const ok = document.execCommand('copy')
      area.remove()
      return ok
    } catch {
      return false
    }
  }
}
