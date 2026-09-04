type BadgeLevel = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW' | 'UNKNOWN'

const LEVEL_STYLES: Record<BadgeLevel, string> = {
  CRITICAL: 'bg-severity-critical-bg text-severity-critical border-severity-critical-border',
  HIGH: 'bg-severity-high-bg text-severity-high border-severity-high-border',
  MEDIUM: 'bg-severity-medium-bg text-severity-medium border-severity-medium-border',
  LOW: 'bg-severity-low-bg text-severity-low border-severity-low-border',
  UNKNOWN: 'bg-slate-100 text-slate-500 border-slate-200',
}

function normalize(value: string | null | undefined): BadgeLevel {
  const v = (value ?? '').toUpperCase()
  if (v === 'CRITICAL' || v === 'HIGH' || v === 'MEDIUM' || v === 'LOW') return v
  return 'UNKNOWN'
}

interface RiskBadgeProps {
  level: string | null | undefined
  className?: string
}

/** Shared badge for both decision `severity` (CRITICAL/HIGH/MEDIUM/LOW)
 * and ML `risk_level` (Low/Medium/High) -- same restrained palette, case
 * normalized. */
export function RiskBadge({ level, className = '' }: RiskBadgeProps) {
  const normalized = normalize(level)
  const label = level ?? 'Unknown'
  return (
    <span
      className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${LEVEL_STYLES[normalized]} ${className}`}
    >
      {label}
    </span>
  )
}
