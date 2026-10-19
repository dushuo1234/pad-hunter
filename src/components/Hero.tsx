import { RadarGraphic } from './RadarGraphic'
import { formatNumber } from '../utils/format'

interface HeroProps {
  projectCount: number
  categoryCount: number
  chainCount: number
  generatedAt?: string
  source?: string
}

function sourceLabel(source?: string): string | undefined {
  if (!source) return undefined
  if (source.startsWith('telegram:')) return `Telegram「${source.slice('telegram:'.length)}」`
  return source
}

export function Hero({ projectCount, categoryCount, chainCount, generatedAt, source }: HeroProps) {
  const sourceText = sourceLabel(source)
  return (
    <section className="relative overflow-hidden border-b border-[var(--color-line)] dark:border-[var(--color-night-line)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(232,135,58,0.08),transparent_55%)] dark:bg-[radial-gradient(ellipse_at_top_right,rgba(232,135,58,0.12),transparent_55%)]" />

      <div className="relative mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 sm:py-14 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <div>
          <p className="mb-3 font-mono text-[11px] tracking-[0.18em] text-[var(--color-orange)]">
            Telegram · 项目推送
          </p>
          <h1 className="text-3xl font-extrabold leading-[1.15] tracking-tight text-[var(--color-ink)] sm:text-4xl lg:text-[2.75rem] dark:text-[var(--color-night-ink)]">
            按链、按类型
            <br />
            <span className="text-[var(--color-orange)]">看清今天推送的项目</span>
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
            台子雷达读取 Telegram「项目推送」卡片，按
            <strong className="font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]"> 链 </strong>
            和
            <strong className="font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]"> 类型 / 发射台 </strong>
            排开。状态、开盘和风险写在卡片上。数据来自 JSON，按日刷新，不用登录。
          </p>

          <div className="mt-8 grid grid-cols-3 gap-3 sm:gap-5">
            <Stat value={formatNumber(projectCount)} label="追踪项目" />
            <Stat value={String(categoryCount)} label="类型" />
            <Stat value={String(chainCount)} label="覆盖链" />
          </div>

          {(generatedAt || source) && (
            <p className="mt-4 font-mono text-[11px] text-[var(--color-ink-muted)]">
              {sourceText ? `来源 · ${sourceText}` : '数据'}
              {generatedAt
                ? ` · ${new Date(generatedAt).toLocaleString('zh-CN', {
                    timeZone: 'Asia/Shanghai',
                    hour12: false,
                  })} 北京时间`
                : ''}
            </p>
          )}
        </div>

        <div className="flex justify-center lg:justify-end">
          <RadarGraphic className="opacity-95" />
        </div>
      </div>
    </section>
  )
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-line)] bg-[var(--color-card)] px-3 py-3 shadow-sm dark:border-[var(--color-night-line)] dark:bg-[var(--color-night-card)] sm:px-4">
      <div className="text-xl font-bold tracking-tight text-[var(--color-ink)] sm:text-2xl dark:text-[var(--color-night-ink)]">
        {value}
      </div>
      <div className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-[var(--color-ink-muted)]">
        {label}
      </div>
    </div>
  )
}
