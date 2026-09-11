import { RadarGraphic } from './RadarGraphic'
import { formatNumber } from '../utils/format'

interface HeroProps {
  projectCount: number
  avgScore: number
  chainCount: number
  generatedAt?: string
}

export function Hero({ projectCount, avgScore, chainCount, generatedAt }: HeroProps) {
  return (
    <section className="relative overflow-hidden border-b border-[var(--color-line)] dark:border-[var(--color-night-line)]">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(232,135,58,0.08),transparent_55%)] dark:bg-[radial-gradient(ellipse_at_top_right,rgba(232,135,58,0.12),transparent_55%)]" />

      <div className="relative mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:px-6 sm:py-14 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <div>
          <p className="mb-3 font-mono text-[11px] uppercase tracking-[0.18em] text-[var(--color-orange)]">
            Product Launchpad Hunter
          </p>
          <h1 className="text-3xl font-extrabold leading-[1.15] tracking-tight text-[var(--color-ink)] sm:text-4xl lg:text-[2.75rem] dark:text-[var(--color-night-ink)]">
            在人群之前发现
            <br />
            <span className="text-[var(--color-orange)]">正在建造台子的团队</span>
          </h1>
          <p className="mt-4 max-w-xl text-[15px] leading-relaxed text-[var(--color-ink-soft)] dark:text-[var(--color-night-soft)]">
            台子雷达专注 Launchpad <strong className="font-semibold text-[var(--color-ink)] dark:text-[var(--color-night-ink)]">产品</strong>
            ，不是 pump/pons 上的 meme 代币。扫描 X 上的 builder 信号、粉丝与 KOL 密度，帮你快速筛选值得跟进的垫子团队。
          </p>

          <div className="mt-8 grid grid-cols-3 gap-3 sm:gap-5">
            <Stat value={formatNumber(projectCount)} label="追踪项目" />
            <Stat value={avgScore.toFixed(1)} label="平均评分" />
            <Stat value={String(chainCount)} label="覆盖链" />
          </div>

          {generatedAt && (
            <p className="mt-4 font-mono text-[11px] text-[var(--color-ink-muted)]">
              数据生成 · {new Date(generatedAt).toLocaleString('zh-CN', { timeZone: 'UTC' })} UTC
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
