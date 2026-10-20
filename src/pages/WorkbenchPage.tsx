import { useMemo, useState, type ReactNode } from 'react'
import { useWorkbenchItems } from '../hooks/useWorkbench'
import { monitorPath } from '../router'
import type { Candidate, MonitorEvent } from '../types'
import { categoryOf } from '../utils/categories'
import { decodeSnippet, formatLatency, formatShanghai, shortAddr } from '../utils/format'
import type { MonitorSnapshot } from '../utils/monitor'
import {
  isHandlePinned,
  parseWorkbenchItems,
  pinCandidate,
  pinManual,
  progressForItem,
  removeWorkbenchItem,
  replaceWorkbench,
  searchCatalog,
  updateWorkbenchNotes,
  type WorkbenchItem,
} from '../utils/workbench'

interface WorkbenchPageProps {
  candidates: Candidate[]
  events: MonitorEvent[]
  loading: boolean
  eventsAt?: string
}

const FIELD =
  'h-10 w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]'

export function WorkbenchPage({ candidates, events, loading, eventsAt }: WorkbenchPageProps) {
  const items = useWorkbenchItems()
  const [catalogOpen, setCatalogOpen] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [manual, setManual] = useState({ name: '', handle: '', siteUrl: '', ca: '', caChain: '' })

  const matches = useMemo(() => searchCatalog(candidates, query), [candidates, query])

  const onManualSubmit = (event: { preventDefault: () => void }) => {
    event.preventDefault()
    try {
      const result = pinManual(manual)
      setMessage(result === 'added' ? `已手动加入 ${manual.name.trim() || manual.handle.trim()}` : '已更新同名钉选，备注保留')
      setManual({ name: '', handle: '', siteUrl: '', ca: '', caChain: '' })
    } catch (error) {
      setMessage(error instanceof Error ? error.message : '无法添加')
    }
  }

  const onImport = async (file: File) => {
    try {
      const parsed = parseWorkbenchItems(JSON.parse(await file.text()))
      if (
        items.length > 0 &&
        !window.confirm(`导入 ${parsed.length} 条，将替换当前工作台里的 ${items.length} 条（含备注）。继续？`)
      ) {
        return
      }
      replaceWorkbench(parsed)
      setMessage(parsed.length > 0 ? `已导入 ${parsed.length} 条` : '已导入空工作台')
    } catch (error) {
      setMessage(error instanceof SyntaxError ? '无法解析 JSON' : error instanceof Error ? error.message : '导入失败')
    }
  }

  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">个人看板</p>
      <div className="mt-2 flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
          工作台
        </h1>
        <p className="font-mono text-[11px] text-[var(--color-ink-muted)]">
          {items.length} 个钉选
          {eventsAt ? ` · 监控数据 ${formatShanghai(eventsAt)}` : ''}
        </p>
      </div>
      <p className="mt-3 max-w-3xl text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        把关心的项目钉在这里，写下只属于你的备注，并对照公开监控里的站点、开盘信号、合约和工厂部署。钉选和备注保存在这台浏览器的
        localStorage，不会上传。换设备或清站点数据前，先导出 JSON。
      </p>

      <div className="mt-5 flex flex-wrap gap-2">
        <ToolbarButton pressed={catalogOpen} onClick={() => setCatalogOpen((open) => !open)}>
          从候选加入
        </ToolbarButton>
        <ToolbarButton pressed={manualOpen} onClick={() => setManualOpen((open) => !open)}>
          手动添加
        </ToolbarButton>
        <ToolbarButton
          onClick={() => {
            downloadWorkbench(items)
            setMessage('已导出 JSON')
          }}
        >
          导出 JSON
        </ToolbarButton>
        <label className="cursor-pointer rounded-lg border border-[var(--color-line)] bg-[var(--color-card)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-ink-soft)] transition hover:border-[var(--color-orange)] hover:text-[var(--color-orange-deep)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]">
          导入 JSON
          <input
            type="file"
            name="workbenchImport"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0]
              if (file) void onImport(file)
              event.target.value = ''
            }}
          />
        </label>
      </div>

      {message && (
        <p className="mt-3 font-mono text-xs text-[var(--color-ink-muted)]" role="status">
          {message}
        </p>
      )}

      {catalogOpen && (
        <section className="mt-4 rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
          <label className="flex flex-col gap-1.5" htmlFor="workbench-search">
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
              搜索候选
            </span>
            <input
              id="workbench-search"
              name="catalogSearch"
              type="search"
              autoFocus
              value={query}
              placeholder="名称或 X 账号"
              onChange={(event) => setQuery(event.target.value)}
              className={FIELD}
            />
          </label>
          {!query.trim() && (
            <p className="mt-3 text-xs text-[var(--color-ink-muted)]">输入项目名或 @handle，从当前候选列表里选。</p>
          )}
          {query.trim() && matches.length === 0 && (
            <p className="mt-3 text-xs text-[var(--color-ink-muted)]">没有匹配的候选。可以改用手动添加。</p>
          )}
          {matches.length > 0 && (
            <ul className="mt-3 divide-y divide-[var(--color-line)] dark:divide-[var(--color-night-line)]">
              {matches.map((candidate) => {
                const pinned = isHandlePinned(items, candidate.handle)
                return (
                  <li key={`${candidate.source ?? ''}-${candidate.handle}`} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
                        {candidate.name}
                      </p>
                      <p className="truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
                        @{candidate.handle} · {categoryOf(candidate)} · {candidate.chain || '链未标注'}
                      </p>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        const result = pinCandidate(candidate)
                        setMessage(result === 'added' ? `已加入 ${candidate.name}` : `已更新 ${candidate.name}，备注保留`)
                      }}
                      className="shrink-0 rounded-full bg-[var(--color-orange)] px-3 py-1 text-xs font-semibold text-white hover:bg-[var(--color-orange-deep)]"
                    >
                      {pinned ? '已加入' : '加入'}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      )}

      {manualOpen && (
        <form
          onSubmit={onManualSubmit}
          className="mt-4 rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="名称" htmlFor="workbench-name">
              <input
                id="workbench-name"
                name="name"
                value={manual.name}
                onChange={(event) => setManual((current) => ({ ...current, name: event.target.value }))}
                className={FIELD}
                placeholder="项目名"
              />
            </Field>
            <Field label="X 账号" htmlFor="workbench-handle">
              <input
                id="workbench-handle"
                name="handle"
                value={manual.handle}
                onChange={(event) => setManual((current) => ({ ...current, handle: event.target.value }))}
                className={FIELD}
                placeholder="可选，例如 hypeqfun"
              />
            </Field>
            <Field label="站点" htmlFor="workbench-site">
              <input
                id="workbench-site"
                name="siteUrl"
                value={manual.siteUrl}
                onChange={(event) => setManual((current) => ({ ...current, siteUrl: event.target.value }))}
                className={FIELD}
                placeholder="可选，https://"
              />
            </Field>
            <Field label="CA / 链" htmlFor="workbench-ca">
              <div className="grid grid-cols-[minmax(0,1fr)_7rem] gap-2">
                <input
                  id="workbench-ca"
                  name="ca"
                  value={manual.ca}
                  onChange={(event) => setManual((current) => ({ ...current, ca: event.target.value }))}
                  className={`${FIELD} font-mono text-xs`}
                  placeholder="可选合约"
                />
                <input
                  id="workbench-chain"
                  name="caChain"
                  aria-label="链"
                  value={manual.caChain}
                  onChange={(event) => setManual((current) => ({ ...current, caChain: event.target.value }))}
                  className={FIELD}
                  placeholder="链"
                />
              </div>
            </Field>
          </div>
          <button
            type="submit"
            className="mt-3 rounded-lg bg-[var(--color-orange)] px-3 py-2 text-xs font-semibold text-white hover:bg-[var(--color-orange-deep)]"
          >
            添加到工作台
          </button>
        </form>
      )}

      {items.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] px-4 py-14 text-center dark:border-[var(--color-night-line)]">
          <p className="text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">工作台还是空的。</p>
          <p className="mx-auto mt-2 max-w-lg text-xs leading-relaxed text-[var(--color-ink-muted)]">
            从候选列表搜索名称或 X 账号加入，或手动填一个项目。这些钉选和备注只存在本机 localStorage，站点本身没有账号。导出
            JSON 用来备份；导入 JSON 会替换当前工作台。
          </p>
        </div>
      ) : (
        <ul className="mt-6 space-y-4">
          {items.map((item) => (
            <WorkbenchCard
              key={item.id}
              item={item}
              candidates={candidates}
              events={events}
              loading={loading}
            />
          ))}
        </ul>
      )}
    </main>
  )
}

function WorkbenchCard({
  item,
  candidates,
  events,
  loading,
}: {
  item: WorkbenchItem
  candidates: Candidate[]
  events: MonitorEvent[]
  loading: boolean
}) {
  const progress = useMemo(() => progressForItem(item, candidates, events), [item, candidates, events])
  const { candidate, snap, eventCount } = progress
  const siteHref = item.siteUrl || candidate?.sites?.[0] || ''

  return (
    <li className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 shadow-sm dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] sm:p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="truncate text-base font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
              {item.name}
            </h2>
            <span className="rounded-md bg-[var(--color-cream-2)] px-1.5 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]">
              {item.origin === 'manual' ? '手动' : '候选'}
            </span>
            {candidate?.status && <Meta>{candidate.status}</Meta>}
            {candidate?.listing && <Meta>{candidate.listing}</Meta>}
          </div>
          <p className="mt-1 truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
            {item.handle ? `@${item.handle}` : '未填 X 账号'}
            {candidate ? ` · ${categoryOf(candidate)} · ${candidate.chain}` : item.caChain ? ` · ${item.caChain}` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={() => removeWorkbenchItem(item.id)}
          className="shrink-0 text-xs text-[var(--color-ink-muted)] hover:text-[var(--color-orange-deep)] dark:hover:text-[var(--color-orange)]"
        >
          移出
        </button>
      </div>

      <label className="mt-4 block" htmlFor={`note-${item.id}`}>
        <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">备注</span>
        <textarea
          id={`note-${item.id}`}
          name={`notes-${item.id}`}
          value={item.notes}
          rows={3}
          placeholder="写下你自己的观察。输入后即保存在这台浏览器。"
          onChange={(event) => updateWorkbenchNotes(item.id, event.target.value)}
          className="mt-1.5 w-full resize-y rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 py-2 text-sm leading-relaxed outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
        />
      </label>

      <div className="mt-4">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">实时监控进度</h3>
          <span className="font-mono text-[11px] text-[var(--color-ink-muted)]">
            {item.handle ? `${eventCount} 条事件` : '无法对照'}
          </span>
        </div>
        {loading && candidates.length === 0 ? (
          <p className="text-xs text-[var(--color-ink-muted)]">正在读取公开监控数据…</p>
        ) : (
          <ProgressGrid snap={snap} item={item} candidate={candidate} />
        )}
        {!item.handle && (
          <p className="mt-2 text-xs leading-relaxed text-[var(--color-ink-muted)]">
            没有 X 账号，对不上 candidates.json 和 monitor_events.json。补上 handle 后再加入，就能看到监控详情。
          </p>
        )}
        {item.handle && !candidate && eventCount === 0 && !loading && (
          <p className="mt-2 text-xs leading-relaxed text-[var(--color-ink-muted)]">
            公开数据里还没有 @{item.handle}。刷新后如果监控写入了同名 handle，进度会显示在这里。
          </p>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-3 text-sm">
          {item.handle && (
            <a href={monitorPath(item.handle)} className="font-mono text-[11px] font-medium text-[var(--color-orange)] hover:underline">
              监控详情
            </a>
          )}
          {siteHref && (
            <a href={siteHref} target="_blank" rel="noreferrer" className="truncate font-mono text-[11px] text-[var(--color-orange)] hover:underline">
              {siteHref.replace(/^https?:\/\//, '')}
            </a>
          )}
        </div>
      </div>
    </li>
  )
}

function ProgressGrid({
  snap,
  item,
  candidate,
}: {
  snap: MonitorSnapshot
  item: WorkbenchItem
  candidate?: Candidate
}) {
  const site = snap.lastSite
  const knownSite = Boolean(item.siteUrl || candidate?.sites?.length)
  const siteText = site
    ? [
        site.status === 'up' ? '可用' : site.status === 'down' ? '不可用' : '已探测',
        formatLatency(site.timeS),
        formatShanghai(site.at),
      ]
        .filter(Boolean)
        .join(' · ')
    : knownSite
      ? '有站点，尚未探测'
      : '无站点'
  const signal = snap.lastSignal?.text
  const ca = snap.ca || item.ca
  const factory = snap.lastFactory

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <Metric
        label="站点"
        value={siteText}
        warn={site?.status === 'down'}
      />
      <Metric label="开盘信号" value={signal ? decodeSnippet(signal) : '无'} clamp />
      <Metric
        label="CA"
        value={ca ? `${shortAddr(ca)}${snap.caChain || item.caChain ? ` · ${snap.caChain || item.caChain}` : ''}` : '未发现'}
        title={ca || undefined}
        mono
      />
      <Metric
        label="工厂"
        value={
          factory
            ? ['有部署', factory.chain, formatShanghai(factory.at)].filter(Boolean).join(' · ')
            : '无'
        }
        title={factory?.tx || factory?.token || undefined}
      />
    </div>
  )
}

function Metric({
  label,
  value,
  title,
  mono,
  warn,
  clamp,
}: {
  label: string
  value: string
  title?: string
  mono?: boolean
  warn?: boolean
  clamp?: boolean
}) {
  return (
    <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-cream)] px-3 py-3 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night)]">
      <div
        title={title ?? value}
        className={`text-sm font-semibold ${
          warn
            ? 'text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]'
            : 'text-[var(--color-ink)] dark:text-[var(--color-night-ink)]'
        } ${clamp ? 'line-clamp-2 text-xs font-medium leading-relaxed' : 'truncate'} ${mono ? 'font-mono text-xs font-medium' : ''}`}
      >
        {value}
      </div>
      <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">{label}</div>
    </div>
  )
}

function Meta({ children }: { children: string }) {
  return (
    <span className="rounded-md border border-[var(--color-line)] px-1.5 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]">
      {children}
    </span>
  )
}

function Field({ label, htmlFor, children }: { label: string; htmlFor: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5" htmlFor={htmlFor}>
      <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">{label}</span>
      {children}
    </label>
  )
}

function ToolbarButton({
  children,
  onClick,
  pressed,
}: {
  children: string
  onClick: () => void
  pressed?: boolean
}) {
  return (
    <button
      type="button"
      aria-pressed={pressed}
      onClick={onClick}
      className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
        pressed
          ? 'border-[var(--color-orange)] bg-[var(--color-orange-soft)] text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.12)] dark:text-[var(--color-orange)]'
          : 'border-[var(--color-line)] bg-[var(--color-card)] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] hover:text-[var(--color-orange-deep)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] dark:text-[var(--color-night-soft)]'
      }`}
    >
      {children}
    </button>
  )
}

function downloadWorkbench(items: WorkbenchItem[]) {
  const payload = {
    version: 1,
    exported_at: new Date().toISOString(),
    items,
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'pad-hunter-workbench.json'
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}
