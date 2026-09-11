export function RadarGraphic({ className = '' }: { className?: string }) {
  return (
    <div className={`relative aspect-square w-full max-w-[340px] ${className}`} aria-hidden>
      <svg viewBox="0 0 320 320" className="h-full w-full">
        <defs>
          <radialGradient id="radarGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#E8873A" stopOpacity="0.18" />
            <stop offset="70%" stopColor="#E8873A" stopOpacity="0.04" />
            <stop offset="100%" stopColor="#E8873A" stopOpacity="0" />
          </radialGradient>
          <linearGradient id="sweepGrad" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#E8873A" stopOpacity="0" />
            <stop offset="70%" stopColor="#E8873A" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#E8873A" stopOpacity="0.7" />
          </linearGradient>
        </defs>

        <circle cx="160" cy="160" r="150" fill="url(#radarGlow)" />
        <circle cx="160" cy="160" r="148" fill="none" className="stroke-[var(--color-line)] dark:stroke-[var(--color-night-line)]" strokeWidth="1.5" />
        <circle cx="160" cy="160" r="110" fill="none" className="stroke-[var(--color-radar-ring)] dark:stroke-[var(--color-night-line)]" strokeWidth="1" strokeDasharray="4 6" />
        <circle cx="160" cy="160" r="72" fill="none" className="stroke-[var(--color-radar-ring)] dark:stroke-[var(--color-night-line)]" strokeWidth="1" />
        <circle cx="160" cy="160" r="36" fill="none" className="stroke-[var(--color-radar-ring)] dark:stroke-[var(--color-night-line)]" strokeWidth="1" />

        <line x1="160" y1="12" x2="160" y2="308" className="stroke-[var(--color-line)] dark:stroke-[var(--color-night-line)]" strokeWidth="1" />
        <line x1="12" y1="160" x2="308" y2="160" className="stroke-[var(--color-line)] dark:stroke-[var(--color-night-line)]" strokeWidth="1" />

        <g className="radar-sweep">
          <path d="M160 160 L160 20 A140 140 0 0 1 280 100 Z" fill="url(#sweepGrad)" opacity="0.85" />
          <line x1="160" y1="160" x2="280" y2="100" stroke="#E8873A" strokeWidth="2" strokeLinecap="round" />
        </g>

        <circle className="radar-dot" cx="210" cy="95" r="4" fill="#E8873A" />
        <circle className="radar-dot" cx="120" cy="70" r="3" fill="#E8873A" />
        <circle className="radar-dot" cx="230" cy="180" r="3.5" fill="#E8873A" />
        <circle className="radar-dot" cx="95" cy="200" r="3" fill="#E8873A" />

        <circle cx="160" cy="160" r="5" fill="#E8873A" />
        <circle cx="160" cy="160" r="9" fill="none" stroke="#E8873A" strokeWidth="1.5" opacity="0.5" />
      </svg>
    </div>
  )
}
