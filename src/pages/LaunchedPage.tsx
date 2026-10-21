import { useState } from 'react'
import { useCaFinds } from '../hooks/useCaFinds'
import { xProfileUrl } from '../utils/format'
import { shortAddr } from '../utils/format'
import { CA_ROLE_ZH, explorerFor } from '../utils/caFinds'
import {
  explorerUrl,
  formatRemovedAt,
  launchLabel,
  matchLaunched,
  type LaunchedItem,
} from '../utils/launched'
import type { CaFind } from '../types'

interface LaunchedPageProps {
  items: LaunchedItem[]
  generatedAt?: string
  loading: boolean
}

export function LaunchedPage({ items, generatedAt, loading }: LaunchedPageProps) {
  const { launchedArchive } = useCaFinds()
  return (
    <main className="mx-auto max-w-6xl px-4 py-8 sm:px-6">
      <p className="font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">已从主列表归档</p>
      <h1 className="mt-2 text-3xl font-extrabold tracking-tight text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">
        已开盘
      </h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
        监控确认已经开盘的项目会从主列表移出，记在这里。发现记录里确认过的合约会写在对应卡片上。按移出时间从新到旧排列。开盘时间没有记录时显示「未知」。
        {generatedAt ? ` 归档时间 ${formatRemovedAt(generatedAt)}。` : ''}
      </p>

      {loading && items.length === 0 ? (
        <div className="mt-8 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          加载已开盘…
        </div>
      ) : items.length === 0 ? (
        <div className="mt-6 rounded-2xl border border-dashed border-[var(--color-line)] py-16 text-center text-sm text-[var(--color-ink-muted)] dark:border-[var(--color-night-line)]">
          还没有归档的已开盘项目。
        </div>
      ) : (
        <ul className="mt-6 space-y-3">
          {items.map((item, index) => (
            <LaunchedCard
              key={`${item.handle || item.project}-${item.removedAt}-${index}`}
              item={item}
              records={launchedArchive.filter(
                (row) => row.caStatus === 'confirmed' && matchLaunched([item], row) != null,
              )}
            />
          ))}
        </ul>
      )}
    </main>
  )
}

function LaunchedCard({ item, records }: { item: LaunchedItem; records: CaFind[] }) {
  const name = item.project || item.handle || '未命名'
  const profile = item.xUrl || (item.handle ? xProfileUrl(item.handle) : '')
  const when = launchLabel(item.listingAt)
  const primary = item.ca?.trim().toLowerCase() ?? ''
  const primaryRecord = records.find((row) => row.address.toLowerCase() === primary)
  const extra = records.filter((row) => row.address.toLowerCase() !== primary)
  const explorer = item.ca ? explorerUrl(item.ca, item.caChain || item.chain) : null
  return (
    <li className="rounded-2xl border border-[var(--color-line)] bg-[var(--color-card)] px-4 py-4 dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            {profile ? (
              <a
                href={profile}
                target="_blank"
                rel="noreferrer"
                className="truncate text-sm font-semibold text-[var(--color-ink)] hover:text-[var(--color-orange-deep)] dark:text-[var(--color-night-ink)] dark:hover:text-[var(--color-orange)]"
              >
                {name}
              </a>
            ) : (
              <span className="truncate text-sm font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{name}</span>
            )}
            <span className="rounded-md bg-[var(--color-orange-soft)] px-2 py-0.5 text-[11px] font-medium text-[var(--color-orange-deep)] dark:bg-[rgba(232,135,58,0.15)] dark:text-[var(--color-orange)]">
              已开盘
            </span>
            {item.chain && (
              <span className="rounded-md border border-[var(--color-line)] px-2 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]">
                {item.chain}
              </span>
            )}
            {item.category && (
              <span className="rounded-md border border-[var(--color-line)] px-2 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]">
                {item.category}
              </span>
            )}
          </div>
          <p className="mt-1 truncate font-mono text-[11px] text-[var(--color-ink-muted)]">
            {item.handle ? `@${item.handle}` : '无 X 账号'}
          </p>
        </div>
        <div className="text-right">
          <div className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">移出时间</div>
          <time className="font-mono text-xs text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]" dateTime={item.removedAt || undefined}>
            {formatRemovedAt(item.removedAt)}
          </time>
        </div>
      </div>

      <dl className="mt-4 grid gap-3 sm:grid-cols-2">
        <Field label="开盘时间" value={when} />
        <div>
          <dt className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">CA</dt>
          {item.ca ? (
            <dd className="mt-1 flex flex-wrap items-center gap-2">
              <span className="font-mono text-sm text-[var(--color-ink)] dark:text-[var(--color-night-ink)]" title={item.ca}>
                {shortAddr(item.ca)}
                {item.caChain ? ` · ${item.caChain}` : ''}
              </span>
              {primaryRecord?.caRole && CA_ROLE_ZH[primaryRecord.caRole] && (
                <span className="rounded-md border border-[var(--color-line)] px-1.5 py-0.5 text-[11px] text-[var(--color-ink-soft)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]">
                  {CA_ROLE_ZH[primaryRecord.caRole]}
                </span>
              )}
              {primaryRecord?.provenanceZh && (
                <span className="text-[11px] text-[var(--color-ink-muted)]">{primaryRecord.provenanceZh}</span>
              )}
              <CopyButton value={item.ca} />
              {explorer && (
                <a href={explorer} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-[var(--color-orange)] hover:underline">
                  浏览器
                </a>
              )}
            </dd>
          ) : (
            <dd className="mt-1 text-sm text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">未发现</dd>
          )}
          {extra.length > 0 && (
            <ul className="mt-2 space-y-1">
              {extra.map((row) => {
                const link = explorerFor(row.chain, row.address)
                const role = row.caRole ? CA_ROLE_ZH[row.caRole] : ''
                return (
                  <li key={`${row.chain}-${row.address}`} className="flex flex-wrap items-center gap-2 font-mono text-[11px] text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
                    <span>{role || row.labelZh || '合约'}</span>
                    <span title={row.address}>{shortAddr(row.address)}</span>
                    {row.provenanceZh && <span className="text-[var(--color-ink-muted)]">{row.provenanceZh}</span>}
                    <CopyButton value={row.address} />
                    {link && (
                      <a href={link.url} target="_blank" rel="noreferrer" className="text-[var(--color-orange)] hover:underline">
                        {link.label}
                      </a>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </div>
        <Field label="原因" value={item.reason || '无'} />
        <Field label="依据" value={item.evidence || '无'} />
      </dl>

      {item.sites.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {item.sites.map((site) => (
            <li key={site}>
              <a href={site} target="_blank" rel="noreferrer" className="font-mono text-[11px] text-[var(--color-orange)] hover:underline">
                {site.replace(/^https?:\/\//, '')}
              </a>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">{label}</dt>
      <dd className="mt-1 break-words text-sm text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">{value}</dd>
    </div>
  )
}

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard.writeText(value).then(
          () => {
            setCopied(true)
            window.setTimeout(() => setCopied(false), 1200)
          },
          () => setCopied(false),
        )
      }}
      className="rounded-md border border-[var(--color-line)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--color-ink-soft)] hover:border-[var(--color-orange)] dark:border-[var(--color-night-line)] dark:text-[var(--color-night-soft)]"
    >
      {copied ? '已复制' : '复制'}
    </button>
  )
}
