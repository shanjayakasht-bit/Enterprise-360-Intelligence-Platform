import type { LucideIcon } from 'lucide-react'

export type IndicatorTone = 'positive' | 'neutral' | 'negative'

const TONE_STYLES: Record<IndicatorTone, string> = {
  positive: 'text-severity-low bg-severity-low-bg',
  neutral: 'text-slate-600 bg-slate-100',
  negative: 'text-severity-critical bg-severity-critical-bg',
}

interface KpiCardProps {
  label: string
  value: string
  context?: string
  icon?: LucideIcon
  /** Only rendered when the caller has a real, threshold-derived status to
   * show (e.g. health score >= 70 => "Healthy") -- never a fabricated
   * period-over-period trend, since the API doesn't expose historical KPI
   * snapshots to compute one honestly. */
  indicator?: { label: string; tone: IndicatorTone }
}

export function KpiCard({ label, value, context, icon: Icon, indicator }: KpiCardProps) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5 shadow-card transition hover:shadow-card-hover">
      <div className="flex items-start justify-between">
        <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
        {Icon && (
          <span className="rounded-lg bg-brand-50 p-1.5 text-brand-600">
            <Icon className="h-4 w-4" />
          </span>
        )}
      </div>
      <p className="mt-2 text-2xl font-semibold tracking-tight text-slate-900">{value}</p>
      <div className="mt-2 flex items-center gap-2">
        {context && <p className="text-xs text-slate-500">{context}</p>}
        {indicator && (
          <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${TONE_STYLES[indicator.tone]}`}>
            {indicator.label}
          </span>
        )}
      </div>
    </div>
  )
}
