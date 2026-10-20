import { useCallback, useMemo, useState, type ReactNode } from 'react'
import { WorkbenchDetailModal } from '../components/WorkbenchDetailModal'
import { useWorkbenchLive } from '../hooks/useWorkbenchLive'
import type { Candidate, MonitorEvent } from '../types'
import { formatShanghai } from '../utils/format'
import {
  handleKey,
  isHandlePinned,
  parseWorkbenchItems,
  pinCandidate,
  pinManual,
  removeWorkbenchItem,
  removeWorkbenchItems,
  replaceWorkbench,
  searchCatalog,
  setWorkbenchPush,
  updateWorkbenchNotes,
  type WorkbenchItem,
} from '../utils/workbench'
import {
  candidateFor,
  countSummary,
  displayUrl,
  formatAgo,
  formatInterval,
  formatListingAt,
  formatMs,
  hostLabel,
  introFor,
  projectLaunch,
  rowLaunched,
  siteBadge,
  summaryText,
  urlProtocol,
  type PillTone,
} from '../utils/workbenchView'

interface WorkbenchPageProps {
  candidates: Candidate[]
  events: MonitorEvent[]
  loading: boolean
  eventsAt?: string
}

const FIELD =
  'h-10 w-full rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 text-sm outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]'

export function WorkbenchPage({ candidates, events, loading, eventsAt }: WorkbenchPageProps) {
  const live = useWorkbenchLive(candidates)
  const items = live.items
  const [catalogOpen, setCatalogOpen] = useState(false)
  const [manualOpen, setManualOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(() => !live.token)
  const [query, setQuery] = useState('')
  const [tableQuery, setTableQuery] = useState('')
  const [message, setMessage] = useState<string | null>(null)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [draftToken, setDraftToken] = useState(live.settings.token)
  const [draftBase, setDraftBase] = useState(live.settings.baseUrl)
  const [manual, setManual] = useState({ name: '', handle: '', siteUrl: '', ca: '', caChain: '' })
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set())
  const [notesOpen, setNotesOpen] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const closeDetail = useCallback(() => setDetailId(null), [])

  const matches = useMemo(() => searchCatalog(candidates, query), [candidates, query])
  const needle = tableQuery.trim().toLowerCase()
  const visible = useMemo(() => {
    if (!needle) return items
    return items.filter((item) => {
      const candidate = candidateFor(item, candidates)
      const status = live.statusByHandle.get(handleKey(item.handle))
      const url = displayUrl(item, candidate, status)
      const hay = `${item.name} ${item.handle} ${url} ${introFor(candidate)}`.toLowerCase()
      return hay.includes(needle)
    })
  }, [candidates, items, live.statusByHandle, needle])

  const summary = countSummary(
    items.map((item) => live.statusByHandle.get(handleKey(item.handle))),
    live.hasStatus,
  )
  const detailItem = detailId ? items.find((item) => item.id === detailId) ?? null : null
  const allVisibleSelected = visible.length > 0 && visible.every((item) => selected.has(item.id))
  const someVisibleSelected = visible.some((item) => selected.has(item.id))

  const openSettings = () => {
    setDraftToken(live.settings.token)
    setDraftBase(live.settings.baseUrl)
    setSettingsError(null)
    setSettingsOpen(true)
  }

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
      setSelected(new Set())
      setMessage(parsed.length > 0 ? `已导入 ${parsed.length} 条` : '已导入空工作台')
    } catch (error) {
      setMessage(error instanceof SyntaxError ? '无法解析 JSON' : error instanceof Error ? error.message : '导入失败')
    }
  }

  const onSaveSettings = (event: { preventDefault: () => void }) => {
    event.preventDefault()
    try {
      live.saveSettings({ token: draftToken, baseUrl: draftBase })
      setSettingsError(null)
      setMessage('已保存监控接口设置')
    } catch (error) {
      setSettingsError(error instanceof Error ? error.message : '无法保存')
    }
  }

  const toggleSelected = (id: string) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAllVisible = () => {
    setSelected((current) => {
      const next = new Set(current)
      if (allVisibleSelected) {
        for (const item of visible) next.delete(item.id)
      } else {
        for (const item of visible) next.add(item.id)
      }
      return next
    })
  }

  const removeSelected = () => {
    const ids = [...selected].filter((id) => items.some((item) => item.id === id))
    if (ids.length === 0) return
    if (!window.confirm(`移出选中的 ${ids.length} 个目标？备注会一起删除。`)) return
    removeWorkbenchItems(ids)
    setSelected(new Set())
    if (detailId && ids.includes(detailId)) setDetailId(null)
    setMessage(`已移出 ${ids.length} 个目标`)
  }

  const healthLabel =
    live.healthState === 'online' ? '在线' : live.healthState === 'offline' ? '离线' : '连接中'
  const pollerNote = live.health?.pollerAlive === false ? ' · 轮询未运行' : ''

  return (
    <main className="mx-auto max-w-[1440px] px-4 py-6 sm:px-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">个人看板</p>
          <h1 className="mt-1 text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
            工作台
          </h1>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 font-medium ${
              live.healthState === 'online'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200'
                : live.healthState === 'offline'
                  ? 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200'
                  : 'border-[var(--color-line)] text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]'
            }`}
          >
            <span
              className={`h-1.5 w-1.5 rounded-full ${
                live.healthState === 'online' ? 'bg-emerald-500' : live.healthState === 'offline' ? 'bg-rose-500' : 'bg-[var(--color-ink-muted)]'
              }`}
            />
            接口{healthLabel}
            {pollerNote}
          </span>
          <span className="font-mono text-[11px] text-[var(--color-ink-muted)]">
            公开监控 {events.length} 条{eventsAt ? ` · ${formatShanghai(eventsAt)}` : ''}
          </span>
        </div>
      </div>

      {!live.token && (
        <button
          type="button"
          onClick={openSettings}
          className="mt-4 flex w-full items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-left text-sm text-amber-950 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-100"
        >
          <span aria-hidden="true">!</span>
          请填写监控接口令牌
        </button>
      )}
      {live.authError && (
        <p className="mt-3 rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-100" role="status">
          令牌无效或缺失
        </p>
      )}

      <section className="mt-4 rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
        <button
          type="button"
          aria-expanded={settingsOpen}
          onClick={() => (settingsOpen ? setSettingsOpen(false) : openSettings())}
          className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        >
          <span className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">监控接口</span>
          <span className="font-mono text-[11px] text-[var(--color-ink-muted)]">{settingsOpen ? '收起' : '设置令牌'}</span>
        </button>
        {settingsOpen && (
          <form onSubmit={onSaveSettings} className="border-t border-[var(--color-line)] px-4 py-4 dark:border-[var(--color-night-line)]">
            <p className="max-w-3xl text-xs leading-relaxed text-[var(--color-ink-muted)]">
              令牌只保存在这台浏览器的 localStorage，不会写进页面代码。接口在线状态来自 /health，不需要令牌。
            </p>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
              <Field label="接口令牌" htmlFor="workbench-token">
                <input
                  id="workbench-token"
                  name="pad-hunter-token"
                  type="password"
                  autoComplete="off"
                  value={draftToken}
                  placeholder="粘贴 X-Pad-Hunter-Token"
                  onChange={(event) => setDraftToken(event.target.value)}
                  className={FIELD}
                />
              </Field>
              <Field label="接口地址" htmlFor="workbench-base">
                <input
                  id="workbench-base"
                  name="workbenchBase"
                  type="url"
                  value={draftBase}
                  placeholder={live.defaultBase}
                  onChange={(event) => setDraftBase(event.target.value)}
                  className={FIELD}
                />
              </Field>
            </div>
            <p className="mt-2 font-mono text-[11px] text-[var(--color-ink-muted)]">
              留空则使用 {live.defaultBase}
              {live.health?.version ? ` · 版本 ${live.health.version}` : ''}
              {live.health?.workbenchCount != null ? ` · 服务端 ${live.health.workbenchCount} 个目标` : ''}
              {live.health?.pollerTargetMode ? ` · ${live.health.pollerTargetMode}` : ''}
            </p>
            {settingsError && <p className="mt-2 text-xs text-rose-700 dark:text-rose-300">{settingsError}</p>}
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="submit" className="rounded-lg bg-[var(--color-orange)] px-3 py-2 text-xs font-semibold text-white hover:bg-[var(--color-orange-deep)]">
                保存
              </button>
              {live.token && (
                <button
                  type="button"
                  onClick={() => {
                    live.clearToken()
                    setDraftToken('')
                    setMessage('已清除令牌')
                  }}
                  className="rounded-lg border border-[var(--color-line)] px-3 py-2 text-xs font-medium text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]"
                >
                  清除令牌
                </button>
              )}
            </div>
          </form>
        )}
      </section>

      {(message || live.syncState === 'syncing' || live.syncMessage || live.statusError || live.actionError) && (
        <p className="mt-3 font-mono text-xs text-[var(--color-ink-muted)]" role="status">
          {[message, live.syncState === 'syncing' ? '正在同步…' : live.syncMessage, live.statusError, live.actionError]
            .filter(Boolean)
            .join(' · ')}
        </p>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <input
          type="search"
          name="workbenchTableSearch"
          value={tableQuery}
          placeholder="搜索名称或 URL"
          onChange={(event) => setTableQuery(event.target.value)}
          aria-label="搜索名称或 URL"
          className={`${FIELD} max-w-xs`}
        />
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
        {someVisibleSelected && (
          <ToolbarButton onClick={removeSelected}>移出选中</ToolbarButton>
        )}
      </div>

      {catalogOpen && (
        <section className="mt-4 rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] p-4 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
          <label className="flex flex-col gap-1.5" htmlFor="workbench-search">
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">搜索候选</span>
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
          {loading && candidates.length === 0 && <p className="mt-3 text-xs text-[var(--color-ink-muted)]">正在读取候选…</p>}
          {!query.trim() && <p className="mt-3 text-xs text-[var(--color-ink-muted)]">输入项目名或 @handle，从当前候选列表里选。</p>}
          {query.trim() && matches.length === 0 && !loading && (
            <p className="mt-3 text-xs text-[var(--color-ink-muted)]">没有匹配的候选。可以改用手动添加。</p>
          )}
          {matches.length > 0 && (
            <ul className="mt-3 divide-y divide-[var(--color-line)] dark:divide-[var(--color-night-line)]">
              {matches.map((candidate) => {
                const pinned = isHandlePinned(items, candidate.handle)
                return (
                  <li key={`${candidate.source ?? ''}-${candidate.handle}`} className="flex items-center justify-between gap-3 py-2.5">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{candidate.name}</p>
                      <p className="truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
                        @{candidate.handle} · {candidate.chain || '链未标注'}
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
          <button type="submit" className="mt-3 rounded-lg bg-[var(--color-orange)] px-3 py-2 text-xs font-semibold text-white hover:bg-[var(--color-orange-deep)]">
            添加到工作台
          </button>
        </form>
      )}

      <p className="mt-4 text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        {summaryText(summary.online, summary.offline, items.length, summary.contracts)}
      </p>

      {items.length === 0 ? (
        <div className="mt-4 rounded-2xl border border-dashed border-[var(--color-line)] px-4 py-14 text-center dark:border-[var(--color-night-line)]">
          <p className="text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">工作台还是空的。</p>
          <p className="mx-auto mt-2 max-w-lg text-xs leading-relaxed text-[var(--color-ink-muted)]">
            从候选列表搜索名称或 X 账号加入，或手动填一个项目。钉选、备注和推送开关保存在这台浏览器。填了令牌之后才会同步到监控接口。
          </p>
        </div>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
          <table className="w-full min-w-[1180px] border-collapse text-left">
            <caption className="sr-only">工作台钉选项目</caption>
            <thead className="bg-[var(--color-cream-2)] text-[11px] text-[var(--color-ink-muted)] dark:bg-[var(--color-night-2)]">
              <tr>
                <th scope="col" className="w-10 px-3 py-2">
                  <input
                    type="checkbox"
                    aria-label="全选"
                    checked={allVisibleSelected}
                    ref={(node) => {
                      if (node) node.indeterminate = someVisibleSelected && !allVisibleSelected
                    }}
                    onChange={toggleAllVisible}
                  />
                </th>
                <th scope="col" className="px-2 py-2 font-medium">名称</th>
                <th scope="col" className="px-2 py-2 font-medium">URL</th>
                <th scope="col" className="px-2 py-2 font-medium">推特</th>
                <th scope="col" className="px-2 py-2 font-medium">项目上线</th>
                <th scope="col" className="px-2 py-2 font-medium">站点状态</th>
                <th scope="col" className="px-2 py-2 font-medium">上次检查/间隔</th>
                <th scope="col" className="px-2 py-2 font-medium">变更数</th>
                <th scope="col" className="px-2 py-2 font-medium">扫出的地址</th>
                <th scope="col" className="px-2 py-2 font-medium">开盘时间</th>
                <th scope="col" className="px-2 py-2 font-medium">推送</th>
                <th scope="col" className="px-3 py-2 font-medium">操作</th>
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 && (
                <tr>
                  <td colSpan={12} className="px-4 py-8 text-center text-sm text-[var(--color-ink-muted)]">
                    没有匹配的目标
                  </td>
                </tr>
              )}
              {visible.map((item) => {
                const candidate = candidateFor(item, candidates)
                const status = item.handle ? live.statusByHandle.get(handleKey(item.handle)) : undefined
                const url = displayUrl(item, candidate, status)
                const launch = projectLaunch(status, live.now)
                const site = siteBadge(status, live.isChecking(item.handle))
                const checking = live.isChecking(item.handle)
                const ago = status?.lastCheckAt ? formatAgo(status.lastCheckAt, live.now) : ''
                const pace = [formatInterval(status?.intervalS ?? null), formatMs(status?.lastLatencyMs ?? null)].filter(Boolean).join(' · ')
                const launched = rowLaunched(live.launched, item)
                return (
                  <tr key={item.id} className="border-t border-[var(--color-line)] align-top dark:border-[var(--color-night-line)]">
                    <td className="px-3 py-3">
                      <input
                        type="checkbox"
                        aria-label={`选择 ${item.name}`}
                        checked={selected.has(item.id)}
                        onChange={() => toggleSelected(item.id)}
                      />
                    </td>
                    <td className="max-w-[240px] px-2 py-3">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{item.name}</span>
                        {urlProtocol(url) && <Pill tone="muted">{urlProtocol(url)}</Pill>}
                        {launched && <Pill tone="ok">已开盘</Pill>}
                      </div>
                      {introFor(candidate) && (
                        <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-[var(--color-ink-muted)]">{introFor(candidate)}</p>
                      )}
                      <button
                        type="button"
                        onClick={() => setNotesOpen((current) => (current === item.id ? null : item.id))}
                        className="mt-1 text-[11px] text-[var(--color-orange)] hover:underline"
                      >
                        {item.notes ? '备注' : '写备注'}
                      </button>
                      {notesOpen === item.id && (
                        <textarea
                          aria-label={`${item.name} 备注`}
                          value={item.notes}
                          rows={3}
                          placeholder="写下你自己的观察。输入后即保存在这台浏览器。"
                          onChange={(event) => updateWorkbenchNotes(item.id, event.target.value)}
                          className="mt-1.5 w-full min-w-48 resize-y rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-2 py-1.5 text-xs leading-relaxed outline-none focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
                        />
                      )}
                    </td>
                    <td className="max-w-[180px] px-2 py-3">
                      {url ? (
                        <a href={url} target="_blank" rel="noreferrer" title={url} className="block truncate font-mono text-[11px] text-[var(--color-ink-soft)] hover:text-[var(--color-orange)] dark:text-[var(--color-night-soft)]">
                          {hostLabel(url)}
                        </a>
                      ) : (
                        <span className="text-xs text-[var(--color-ink-muted)]">—</span>
                      )}
                    </td>
                    <td className="px-2 py-3">
                      {item.handle ? (
                        <a
                          href={`https://x.com/${item.handle.replace(/^@/, '')}`}
                          target="_blank"
                          rel="noreferrer"
                          className="font-mono text-[11px] text-[var(--color-orange)] hover:underline"
                        >
                          @{item.handle.replace(/^@/, '')}
                        </a>
                      ) : (
                        <span className="text-xs text-[var(--color-ink-muted)]">—</span>
                      )}
                    </td>
                    <td className="px-2 py-3">
                      <Pill tone={launch.tone}>{launch.label}</Pill>
                    </td>
                    <td className="px-2 py-3">
                      <Pill tone={site.tone} title={site.title}>{site.label}</Pill>
                    </td>
                    <td className="px-2 py-3">
                      <div className="text-xs text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
                        {checking ? '检查中' : ago || '尚未检查'}
                      </div>
                      <div className="mt-0.5 font-mono text-[10px] text-[var(--color-ink-muted)]">{pace || '—'}</div>
                    </td>
                    <td className="px-2 py-3 font-mono text-sm font-semibold text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]">
                      {status ? status.changeCount : '—'}
                    </td>
                    <td className="px-2 py-3">
                      <button
                        type="button"
                        onClick={() => setDetailId(item.id)}
                        className="rounded-md bg-[var(--color-orange-soft)] px-1.5 py-0.5 font-mono text-[11px] font-medium text-[var(--color-orange-deep)] hover:underline dark:bg-[rgba(232,135,58,0.12)] dark:text-[var(--color-orange)]"
                      >
                        {status ? `地址 ${status.addressCount}` : '地址 —'}
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-2 py-3 text-xs text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
                      {formatListingAt(status?.listingAt || '未知')}
                    </td>
                    <td className="px-2 py-3">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={item.push}
                        aria-label={item.push ? `关闭 ${item.name} 推送` : `开启 ${item.name} 推送`}
                        onClick={() => setWorkbenchPush(item.id, !item.push)}
                        className={`relative h-5 w-9 rounded-full transition ${
                          item.push ? 'bg-[var(--color-orange)]' : 'bg-[var(--color-line)] dark:bg-[var(--color-night-line)]'
                        }`}
                      >
                        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition ${item.push ? 'left-4' : 'left-0.5'}`} />
                      </button>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <button
                        type="button"
                        disabled={checking || !item.handle}
                        onClick={() => void live.checkNow(item.handle)}
                        className="text-xs font-medium text-[var(--color-orange)] hover:underline disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {checking ? '检查中' : '检查'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setDetailId(item.id)}
                        className="ml-3 text-xs font-medium text-[var(--color-orange)] hover:underline"
                      >
                        详情
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {detailItem && (
        <WorkbenchDetailModal
          item={detailItem}
          candidate={candidateFor(detailItem, candidates)}
          status={detailItem.handle ? live.statusByHandle.get(handleKey(detailItem.handle)) : undefined}
          launched={rowLaunched(live.launched, detailItem)}
          checking={live.isChecking(detailItem.handle)}
          token={live.token}
          base={live.base}
          now={live.now}
          detailTick={live.detailTick}
          onClose={closeDetail}
          onCheck={() => void live.checkNow(detailItem.handle)}
          onRemove={() => {
            removeWorkbenchItem(detailItem.id)
            setDetailId(null)
            setMessage(`已移出 ${detailItem.name}`)
          }}
        />
      )}
    </main>
  )
}

function Pill({ tone, children, title }: { tone: PillTone; children: string; title?: string }) {
  const toneClass =
    tone === 'ok'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
      : tone === 'bad'
        ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300'
        : tone === 'warn'
          ? 'bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200'
          : 'bg-[var(--color-cream-2)] text-[var(--color-ink-soft)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]'
  return (
    <span title={title || undefined} className={`inline-flex items-center whitespace-nowrap rounded-md px-1.5 py-0.5 text-[11px] font-medium ${toneClass}`}>
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

function ToolbarButton({ children, onClick, pressed }: { children: string; onClick: () => void; pressed?: boolean }) {
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
