import { useMemo, useState } from 'react'
import { PinWorkbenchButton } from '../components/PinWorkbenchButton'
import { useCaFinds } from '../hooks/useCaFinds'
import { monitorPath } from '../router'
import type { CaFind, CaFindConfidence, Candidate } from '../types'
import {
  caFindKey,
  caSourceLabel,
  chainOptions,
  explorerFor,
  filterCaFinds,
  groupCaFinds,
  LOW_CONFIDENCE_HINT,
  safeEvidenceUrl,
} from '../utils/caFinds'
import { findByHandle } from '../utils/candidates'
import { formatShanghai, xProfileUrl } from '../utils/format'

interface CaPageProps {
  candidates: Candidate[]
}

const FIELD =
  'h-10 w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]'

export function CaPage({ candidates }: CaPageProps) {
  const { finds, generatedAt, lastChecked, loading, error, freshKeys } = useCaFinds()
  const [search, setSearch] = useState('')
  const [chain, setChain] = useState('')
  const [confidence, setConfidence] = useState<'all' | CaFindConfidence>('all')

  const chains = useMemo(() => chainOptions(finds), [finds])
  const matched = useMemo(() => filterCaFinds(finds, { search, chain, confidence: 'all' }), [finds, search, chain])
  const visible = useMemo(
    () => (confidence === 'all' ? matched : matched.filter((find) => find.confidence === confidence)),
    [matched, confidence],
  )
  const groups = useMemo(() => groupCaFinds(visible), [visible])
  const freshCount = useMemo(
    () => visible.filter((find) => freshKeys.has(caFindKey(find))).length,
    [visible, freshKeys],
  )
  const confidenceCounts = useMemo(() => {
    return {
      all: matched.length,
      high: matched.filter((find) => find.confidence === 'high').length,
      low: matched.filter((find) => find.confidence === 'low').length,
    }
  }, [matched])

  const checkedLabel = lastChecked ? formatShanghai(lastChecked, true) : ''
  const generatedLabel = generatedAt ? formatShanghai(generatedAt, true) : ''

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">合约发现</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
          发现CA
        </h1>
        <p className="font-mono text-[11px] text-[var(--color-ink-muted)]" title="Asia/Shanghai">
          {checkedLabel ? `上次检查 ${checkedLabel} 北京时间` : '正在检查…'}
          {generatedLabel ? ` · 数据 ${generatedLabel}` : ''}
        </p>
      </div>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        从站点、前端 JS、X、Telegram 和链上扫到的合约地址，按项目归在一起，新的在前。页面每秒读取{' '}
        <span className="font-mono text-[12px]">public/data/ca_finds.json</span>
        。打开页面之后新出现的行会标成「新」。
      </p>
      <p className="mt-2 max-w-3xl text-xs leading-relaxed text-[var(--color-ink-muted)]">{LOW_CONFIDENCE_HINT}</p>

      {loading && finds.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          正在读取合约发现…
        </div>
      ) : (
        <>
          <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)_auto] lg:items-end">
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
            <div className="flex flex-wrap gap-2" role="group" aria-label="置信度">
              {(
                [
                  ['all', '全部'],
                  ['high', '高置信'],
                  ['low', '低置信'],
                ] as const
              ).map(([id, label]) => {
                const active = confidence === id
                return (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={active}
                    onClick={() => setConfidence(id)}
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition ${
                      active
                        ? 'bg-[var(--color-orange)] text-white'
                        : 'border border-[var(--color-line)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]'
                    }`}
                  >
                    {label}
                    <span className={`font-mono text-[10px] ${active ? 'text-white/80' : 'text-[var(--color-ink-muted)]'}`}>
                      {confidenceCounts[id]}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-[var(--color-ink-muted)]">
            <span>
              {visible.length} 个合约 · {groups.length} 个项目
            </span>
            {freshCount > 0 && (
              <span className="text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]" aria-live="polite">
                本次打开后新增 {freshCount} 条
              </span>
            )}
            {error && <span className="text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]">{error}</span>}
          </div>

          {groups.length === 0 ? (
            <EmptyState filtered={finds.length > 0} />
          ) : (
            <div className="mt-4 flex flex-col gap-4">
              {groups.map((group) => (
                <ProjectGroup
                  key={group.key}
                  project={group.project}
                  handle={group.handle}
                  finds={group.finds}
                  candidates={candidates}
                  freshKeys={freshKeys}
                />
              ))}
            </div>
          )}
        </>
      )}
    </main>
  )
}

function EmptyState({ filtered }: { filtered: boolean }) {
  if (filtered) {
    return (
      <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
        没有符合筛选的合约。
      </div>
    )
  }
  return (
    <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] px-4 py-14 text-center dark:border-[var(--color-night-line)]">
      <p className="text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">还没有发现合约</p>
      <p className="mx-auto mt-2 max-w-lg text-xs leading-relaxed text-[var(--color-ink-muted)]">
        把记录写入 public/data/ca_finds.json 的 finds 数组即可。字段为 project、handle、chain、address、source（site / JS /
        X / TG / on-chain）、evidence_url、detected_at、confidence（high / low）、note。页面每秒会重新读取。
      </p>
    </div>
  )
}

function ProjectGroup({
  project,
  handle,
  finds,
  candidates,
  freshKeys,
}: {
  project: string
  handle: string
  finds: CaFind[]
  candidates: Candidate[]
  freshKeys: Set<string>
}) {
  const name = project || (handle ? `@${handle}` : '未命名项目')
  const candidate = handle ? findByHandle(candidates, handle) : undefined
  return (
    <section className="overflow-hidden rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--color-line)] px-4 py-3 dark:border-[var(--color-night-line)]">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {handle ? (
              <a
                href={monitorPath(handle)}
                className="truncate text-sm font-semibold text-[var(--color-ink)] hover:text-[var(--color-orange-deep)] dark:text-[var(--color-night-ink)] dark:hover:text-[var(--color-orange)]"
              >
                {name}
              </a>
            ) : (
              <h2 className="truncate text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{name}</h2>
            )}
            <span className="font-mono text-[10px] text-[var(--color-ink-muted)]">{finds.length} 个地址</span>
          </div>
          {handle && (
            <a
              href={xProfileUrl(handle)}
              target="_blank"
              rel="noreferrer"
              className="mt-0.5 inline-block font-mono text-[11px] text-[var(--color-ink-muted)] hover:text-[var(--color-orange)]"
            >
              @{handle.replace(/^@/, '')}
            </a>
          )}
        </div>
        {handle && (
          <a href={monitorPath(handle)} className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline">
            监控详情
          </a>
        )}
      </header>
      <ul>
        {finds.map((find) => (
          <FindRow
            key={caFindKey(find)}
            find={find}
            fresh={freshKeys.has(caFindKey(find))}
            candidate={candidate}
            projectName={name}
          />
        ))}
      </ul>
    </section>
  )
}

function FindRow({
  find,
  fresh,
  candidate,
  projectName,
}: {
  find: CaFind
  fresh: boolean
  candidate?: Candidate
  projectName: string
}) {
  const explorer = explorerFor(find.chain, find.address)
  const evidence = safeEvidenceUrl(find.evidence_url)
  const when = formatShanghai(find.detected_at, true)
  return (
    <li
      className={`border-b border-[var(--color-line)] px-4 py-3 last:border-b-0 dark:border-[var(--color-night-line)] ${
        fresh ? 'ca-row-new' : ''
      }`}
    >
      <div className="flex flex-wrap items-center gap-2">
        {fresh && (
          <span className="rounded-md bg-[var(--color-orange)] px-1.5 py-0.5 text-[10px] font-semibold text-white">新</span>
        )}
        <ConfidenceBadge confidence={find.confidence} />
        <SourceBadge source={find.source} />
        {find.chain && (
          <span className="rounded-md border border-[var(--color-line)] bg-[var(--color-cream-2)] px-2 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]">
            {find.chain}
          </span>
        )}
        {when && (
          <time className="font-mono text-[11px] text-[var(--color-ink-muted)]" dateTime={find.detected_at} title="Asia/Shanghai">
            {when} 北京时间
          </time>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <code className="min-w-0 break-all font-mono text-[13px] text-[var(--color-ink)] dark:text-[var(--color-night-ink)]" title={find.address}>
          {find.address}
        </code>
        <CopyButton text={find.address} />
        {explorer && (
          <a href={explorer.url} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-[var(--color-orange)] hover:underline">
            {explorer.label}
          </a>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-2">
        {evidence ? (
          <a href={evidence} target="_blank" rel="noreferrer" className="max-w-full truncate font-mono text-[11px] text-[var(--color-orange)] hover:underline">
            证据 {evidence.replace(/^https?:\/\//, '')}
          </a>
        ) : (
          <span className="font-mono text-[11px] text-[var(--color-ink-muted)]">无证据链接</span>
        )}
        {find.handle && (
          <a href={monitorPath(find.handle)} className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline">
            监控详情
          </a>
        )}
        <PinWorkbenchButton
          candidate={candidate}
          name={find.project || projectName}
          handle={find.handle || candidate?.handle}
          ca={find.address}
          caChain={find.chain}
        />
      </div>
      {find.note && (
        <p className="mt-2 text-xs leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">{find.note}</p>
      )}
    </li>
  )
}

function ConfidenceBadge({ confidence }: { confidence: CaFind['confidence'] }) {
  if (confidence === 'low') {
    return (
      <span
        title={LOW_CONFIDENCE_HINT}
        className="rounded-md border border-dashed border-[#b45309] bg-[#fff7ed] px-2 py-0.5 text-[11px] font-semibold text-[#9a3412] dark:border-[#fdba74] dark:bg-[#431407] dark:text-[#fdba74]"
      >
        低置信 · 第三方图标等弱信号
      </span>
    )
  }
  if (confidence === 'high') {
    return (
      <span className="rounded-md bg-[var(--color-cream-2)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-ink-soft)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]">
        高置信
      </span>
    )
  }
  return (
    <span className="rounded-md border border-[var(--color-line)] px-2 py-0.5 text-[11px] text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
      置信度未标注
    </span>
  )
}

function SourceBadge({ source }: { source: string }) {
  return (
    <span
      title={source || '来源未标注'}
      className="rounded-md border border-[var(--color-line)] bg-[var(--color-cream-2)] px-2 py-0.5 font-mono text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]"
    >
      {caSourceLabel(source)}
    </span>
  )
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
