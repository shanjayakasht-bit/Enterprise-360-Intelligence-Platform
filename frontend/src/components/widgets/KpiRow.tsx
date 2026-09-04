import { Activity, DollarSign, Gauge, ShieldAlert, Users } from 'lucide-react'
import { fetchOverview } from '@/api/overview'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { KpiCard, type IndicatorTone } from '@/components/ui/KpiCard'
import { KpiCardSkeleton } from '@/components/ui/LoadingSkeleton'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatNumber, formatPercent } from '@/lib/format'

function healthIndicator(score: number | null): { label: string; tone: IndicatorTone } | undefined {
  if (score === null) return undefined
  if (score >= 70) return { label: 'Healthy', tone: 'positive' }
  if (score >= 50) return { label: 'Watch', tone: 'neutral' }
  return { label: 'At Risk', tone: 'negative' }
}

function slaIndicator(pct: number | null): { label: string; tone: IndicatorTone } | undefined {
  if (pct === null) return undefined
  if (pct >= 95) return { label: 'On target', tone: 'positive' }
  if (pct >= 85) return { label: 'Below target', tone: 'neutral' }
  return { label: 'Off target', tone: 'negative' }
}

export function KpiRow() {
  const state = useFetch(fetchOverview, [])

  return (
    <AsyncContent
      state={state}
      skeleton={
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, i) => (
            <KpiCardSkeleton key={i} />
          ))}
        </div>
      }
    >
      {(data) => (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
          <KpiCard
            label="Total Revenue"
            value={formatCurrencyCompact(data.total_revenue)}
            context="Won deal value"
            icon={DollarSign}
          />
          <KpiCard
            label="Active Customers"
            value={formatNumber(data.active_customers)}
            context="With an active subscription"
            icon={Users}
          />
          <KpiCard
            label="Projects at Risk"
            value={formatNumber(data.projects_at_risk)}
            context="High/Critical risk, ongoing"
            icon={ShieldAlert}
          />
          <KpiCard
            label="Enterprise Health Score"
            value={data.enterprise_health_score !== null ? data.enterprise_health_score.toFixed(1) : '—'}
            context="Weighted composite, 0–100"
            icon={Gauge}
            indicator={healthIndicator(data.enterprise_health_score)}
          />
          <KpiCard
            label="Support SLA"
            value={formatPercent(data.support_sla_percentage)}
            context="Resolved within target"
            icon={Activity}
            indicator={slaIndicator(data.support_sla_percentage)}
          />
        </div>
      )}
    </AsyncContent>
  )
}
