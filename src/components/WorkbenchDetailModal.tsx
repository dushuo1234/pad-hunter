import { useEffect, useState, type ReactNode } from 'react'
import type { Candidate } from '../types'
import { categoryOf } from '../utils/categories'
import { shortAddr, xProfileUrl } from '../utils/format'
import {
  errorText,
  fetchDetail,
  isAuthError,
  isUnavailable,
  type FoundAddress,
  type WorkbenchDetail,
  type WorkbenchStatusItem,
} from '../utils/workbenchApi'
import type { WorkbenchItem } from '../utils/workbench'
import { reviewSnapshot } from '../utils/reviewed'
import { ConfirmLaunchedButton } from './ConfirmLaunchedButton'
import { PushDate } from './PushDate'
import { ReviewedMark } from './ReviewedMark'
import { observeWorkbenchDetail } from '../utils/caAlert'
import { setWorkbenchPush, updateWorkbenchNotes } from '../utils/workbench'
import {
  catalogListing,
  chainLabel,
  displayUrl,
  explorerFor,
  formatAgo,
  formatBytes,
  formatInterval,
  formatMs,
  formatShanghaiFull,
  introFor,
  projectLaunch,
  siteBadge,
  urlProtocol,
  type PillTone,
} from '../utils/workbenchView'

interface WorkbenchDetailModalProps {
  item: WorkbenchItem
  candidate?: Candidate
  status?: WorkbenchStatusItem
  launched: boolean
  checking: boolean
  token: string
  base: string
  now: number
  detailTick: number
  onClose: () => void
  onCheck: () => void
  onRemove: () => void
}

export function WorkbenchDetailModal({
  item,
  candidate,
  status,
  launched,
  checking,
  token,
  base,
  now,
  detailTick,
  onClose,
  onCheck,
  onRemove,
}: WorkbenchDetailModalProps) {
  const [detail, setDetail] = useState<WorkbenchDetail | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [copied, setCopied] = useState('')

  const chain = chainLabel(item, candidate)
  const url = displayUrl(item, candidate, status)
  const launch = projectLaunch(status, now)
  const site = siteBadge(status, checking)
  const protocol = urlProtocol(url)
  const listing = catalogListing(candidate, status, new Date(now))
  const evidence = listing.evidenceUrl
  const source = listing.source
  const interval = formatInterval(status?.intervalS ?? null)
  const checked = formatShanghaiFull(status?.lastCheckAt)
  const latency = formatMs(status?.lastLatencyMs ?? null)

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    document.addEventListener('keydown', onKey)
    return () => {
      document.body.style.overflow = previous
      document.removeEventListener('keydown', onKey)
    }
  }, [onClose])

  useEffect(() => {
    if (!token || !item.handle) return
    let alive = true
    let timer = 0
    const load = () => {
      setLoading(true)
      void fetchDetail(base, token, item.handle, chain)
        .then((next) => {
          if (!alive) return
          setDetail(next)
          setDetailError(null)
          observeWorkbenchDetail(item.handle, item.name || candidate?.name || '', next.addresses, { launched })
        })
        .catch((error: unknown) => {
          if (!alive) return
          if (isUnavailable(error)) {
            window.clearInterval(timer)
            setDetailError(null)
            return
          }
          setDetailError(isAuthError(error) ? '令牌无效或缺失' : errorText(error))
        })
        .finally(() => {
          if (alive) setLoading(false)
        })
    }
    load()
    timer = window.setInterval(() => {
      if (!document.hidden) load()
    }, 5000)
    return () => {
      alive = false
      window.clearInterval(timer)
    }
  }, [base, chain, candidate?.name, detailTick, item.handle, item.name, launched, token])

  const addresses: FoundAddress[] =
    detail && detail.addresses.length > 0
      ? detail.addresses
      : (status?.lastAddresses ?? []).map((address) => ({ address, chain, label: '' }))
  const crawlCount = status?.crawlCount ?? detail?.crawlCount
  const crawlText = crawlCount != null ? `${crawlCount} 次` : detail ? `${detail.crawlHistory.length} 次` : '—'
  const addressTotal = status?.addressCount ?? addresses.length

  const copyAddress = async (address: string) => {
    try {
      await navigator.clipboard.writeText(address)
    } catch {
      const input = document.createElement('textarea')
      input.value = address
      input.setAttribute('readonly', '')
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      input.remove()
    }
    setCopied(address)
    window.setTimeout(() => setCopied((current) => (current === address ? '' : current)), 1500)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 px-4 py-8 backdrop-enter" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="workbench-detail-title"
        onMouseDown={(event) => event.stopPropagation()}
        className="w-full max-w-lg rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] shadow-xl dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]"
      >
        <div className="flex items-start justify-between gap-3 border-b border-[var(--color-line)] px-4 py-3 dark:border-[var(--color-night-line)]">
          <div className="min-w-0">
            <h2 id="workbench-detail-title" className="truncate text-lg font-bold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
              {item.name}
            </h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              <ReviewedMark
                handle={item.handle}
                name={item.name}
                snapshot={reviewSnapshot({
                  listing_at: candidate?.listing_at,
                  launch_at: candidate?.launch_at,
                  status: candidate?.status,
                  listing: candidate?.listing,
                  ca: candidate?.ca || status?.lastAddresses?.[0],
                })}
              />
              <Pill tone={launch.tone}>{launch.label}</Pill>
              <Pill tone={site.tone}>{site.label}</Pill>
              {protocol && <Pill tone="muted">{protocol}</Pill>}
              <Pill tone={item.push ? 'ok' : 'muted'}>{item.push ? '推送开' : '推送关'}</Pill>
              {launched && <Pill tone="ok">已开盘</Pill>}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭"
            className="rounded-lg px-2 py-1 text-sm text-[var(--color-ink-muted)] hover:bg-[var(--color-cream-2)] hover:text-[var(--color-ink)] dark:hover:bg-[var(--color-night-2)] dark:hover:text-[var(--color-night-ink)]"
          >
            关闭
          </button>
        </div>

        <div className="max-h-[78vh] overflow-y-auto px-4 py-3">
          <dl className="divide-y divide-[var(--color-line)] dark:divide-[var(--color-night-line)]">
            <Info label="网址">
              {url ? (
                <a href={url} target="_blank" rel="noreferrer" className="break-all text-[var(--color-orange)] hover:underline">
                  {url}
                </a>
              ) : (
                '—'
              )}
            </Info>
            <Info label="介绍">{introFor(candidate) || '—'}</Info>
            <Info label="推送日期">
              <PushDate records={[candidate]} variant="value" />
            </Info>
            <Info label="推特">
              {item.handle ? (
                <a href={xProfileUrl(item.handle)} target="_blank" rel="noreferrer" className="text-[var(--color-orange)] hover:underline">
                  @{item.handle.replace(/^@/, '')}
                </a>
              ) : (
                '—'
              )}
            </Info>
            <Info label="链">{chain || '—'}</Info>
            {candidate && <Info label="分类">{categoryOf(candidate)}</Info>}
            <Info label="抓取间隔">{interval || '—'}</Info>
            <Info label="上次检查">
              {checked ? (
                <span>
                  {checked}
                  {latency ? ` · ${latency}` : ''}
                  {status?.httpCode ? ` · HTTP ${status.httpCode}` : ''}
                </span>
              ) : checking ? (
                '检查中'
              ) : (
                '尚未检查'
              )}
            </Info>
            <Info label="开盘时间">
              <span>{listing.text}</span>
              {listing.deferred && (
                <span
                  title={listing.deferredTitle || '开盘时间已过，项目仍未开盘'}
                  className="ml-2 inline-flex items-center rounded-md border border-[#a16207] bg-[#fefce8] px-1.5 py-0.5 text-[11px] font-semibold text-[#854d0e] dark:border-[#fde68a] dark:bg-[#422006] dark:text-[#fde68a]"
                >
                  延期
                </span>
              )}
              {source && <span className="ml-2 text-[var(--color-ink-muted)]">来源 {source}</span>}
              {evidence && (
                <a href={evidence} target="_blank" rel="noreferrer" className="ml-2 text-[var(--color-orange)] hover:underline">
                  来源
                </a>
              )}
            </Info>
            <Info label="累计抓取">{token ? crawlText : '—'}</Info>
            <Info label="发现物">
              <span className="text-[var(--color-orange-deep)] dark:text-[var(--color-orange)]">地址 {addressTotal}</span>
              {status?.lastChangeAt && (
                <span className="ml-2 text-[var(--color-ink-muted)]">最近变更 {formatAgo(status.lastChangeAt, now)}</span>
              )}
            </Info>
          </dl>

          {addresses.length > 0 && (
            <ul className="mt-2 max-h-40 space-y-1.5 overflow-y-auto rounded-xl border border-[var(--color-line)] bg-[var(--color-cream)] p-2 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night)]">
              {addresses.map((found) => {
                const explorer = explorerFor(found.chain || chain, found.address)
                return (
                  <li key={`${found.chain}-${found.address}`} className="flex items-center gap-2 text-xs">
                    <span className="min-w-0 flex-1 truncate font-mono" title={found.address}>
                      {found.chain ? `${found.chain} · ` : ''}
                      {shortAddr(found.address)}
                      {found.label ? ` · ${found.label}` : ''}
                    </span>
                    <button
                      type="button"
                      onClick={() => void copyAddress(found.address)}
                      className="shrink-0 text-[var(--color-orange)] hover:underline"
                    >
                      {copied === found.address ? '已复制' : '复制'}
                    </button>
                    {explorer && (
                      <a href={explorer.url} target="_blank" rel="noreferrer" className="shrink-0 text-[var(--color-orange)] hover:underline">
                        {explorer.label}
                      </a>
                    )}
                  </li>
                )
              })}
            </ul>
          )}

          <label className="mt-4 block" htmlFor={`detail-note-${item.id}`}>
            <span className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">备注</span>
            <textarea
              id={`detail-note-${item.id}`}
              name={`detail-notes-${item.id}`}
              value={item.notes}
              rows={3}
              placeholder="写下你自己的观察。输入后即保存在这台浏览器，并随同步发给监控接口。"
              onChange={(event) => updateWorkbenchNotes(item.id, event.target.value)}
              className="mt-1.5 w-full resize-y rounded-lg border border-[var(--color-line)] bg-[var(--color-cream)] px-3 py-2 text-sm leading-relaxed outline-none transition focus:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-ink)]"
            />
          </label>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <button
              type="button"
              role="switch"
              aria-checked={item.push}
              onClick={() => setWorkbenchPush(item.id, !item.push)}
              className="rounded-lg border border-[var(--color-line)] px-2.5 py-1.5 text-xs font-medium text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]"
            >
              {item.push ? '推送开' : '推送关'}
            </button>
            <button
              type="button"
              onClick={onCheck}
              disabled={checking || !item.handle}
              className="rounded-lg bg-[var(--color-orange)] px-2.5 py-1.5 text-xs font-semibold text-white hover:bg-[var(--color-orange-deep)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              {checking ? '检查中' : '检查'}
            </button>
            <button
              type="button"
              onClick={onRemove}
              className="rounded-lg px-2.5 py-1.5 text-xs text-[var(--color-ink-muted)] hover:text-[var(--color-orange-deep)]"
            >
              移出工作台
            </button>
            {!launched && (
              <ConfirmLaunchedButton handle={item.handle} name={item.name} candidate={candidate} />
            )}
          </div>

          {!token && <p className="mt-3 text-xs text-[var(--color-ink-muted)]">填写监控接口令牌后可查看变更和抓取历史。</p>}
          {token && !item.handle && <p className="mt-3 text-xs text-[var(--color-ink-muted)]">没有 X 账号，监控接口无法按 handle 查询。</p>}
          {detailError && (
            <p className="mt-3 text-xs text-rose-700 dark:text-rose-300" role="status">
              {detailError}
            </p>
          )}
          {loading && !detail && token && <p className="mt-3 text-xs text-[var(--color-ink-muted)]">正在读取详情…</p>}

          <section className="mt-4">
            <h3 className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">最近变更（30）</h3>
            <div className="mt-2 max-h-40 overflow-y-auto rounded-xl border border-[var(--color-line)] dark:border-[var(--color-night-line)]">
              {detail && detail.recentChanges.length > 0 ? (
                <ul className="divide-y divide-[var(--color-line)] px-2 dark:divide-[var(--color-night-line)]">
                  {detail.recentChanges.map((change) => (
                    <li key={change.id} className="flex gap-2 py-2">
                      <span
                        className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${
                          change.tone === 'danger' ? 'bg-rose-500' : change.tone === 'warn' ? 'bg-[var(--color-orange)]' : 'bg-[var(--color-ink-muted)]'
                        }`}
                      />
                      <div className="min-w-0">
                        <p className="break-words text-xs leading-relaxed text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{change.text}</p>
                        {change.at && (
                          <p className="font-mono text-[10px] text-[var(--color-ink-muted)]">
                            {formatAgo(change.at, now) || formatShanghaiFull(change.at) || change.at}
                          </p>
                        )}
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="px-3 py-4 text-xs text-[var(--color-ink-muted)]">暂无变更</p>
              )}
            </div>
          </section>

          <section className="mt-4 pb-1">
            <h3 className="text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">抓取历史（100）</h3>
            <div className="mt-2 max-h-40 overflow-y-auto rounded-xl border border-[var(--color-line)] dark:border-[var(--color-night-line)]">
              {detail && detail.crawlHistory.length > 0 ? (
                <ul className="divide-y divide-[var(--color-line)] px-3 dark:divide-[var(--color-night-line)]">
                  {detail.crawlHistory.map((row) => {
                    const when = formatShanghaiFull(row.at) || row.at
                    const parts = [when, row.httpCode ? `HTTP ${row.httpCode}` : '', formatBytes(row.bytes), formatMs(row.latencyMs)].filter(Boolean)
                    return (
                      <li key={row.id} className="py-1.5 font-mono text-[11px] text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
                        {parts.join(' ') || '—'}
                        {row.error ? <span className="ml-2 text-rose-700 dark:text-rose-300">{row.error}</span> : null}
                      </li>
                    )
                  })}
                </ul>
              ) : (
                <p className="px-3 py-4 text-xs text-[var(--color-ink-muted)]">暂无抓取记录</p>
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)] gap-3 py-2 text-sm">
      <dt className="text-[var(--color-ink-muted)]">{label}</dt>
      <dd className="min-w-0 break-words text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{children}</dd>
    </div>
  )
}

function Pill({ tone, children }: { tone: PillTone; children: string }) {
  const toneClass =
    tone === 'ok'
      ? 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300'
      : tone === 'bad'
        ? 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300'
        : tone === 'warn'
          ? 'bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-200'
          : 'bg-[var(--color-cream-2)] text-[var(--color-ink-soft)] dark:bg-[var(--color-night-2)] dark:text-[var(--color-night-soft)]'
  return <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[11px] font-medium ${toneClass}`}>{children}</span>
}
