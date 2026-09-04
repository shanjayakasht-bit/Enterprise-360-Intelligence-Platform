import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fetchRevenueTrends } from '@/api/revenue'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { ChartCard } from '@/components/ui/ChartCard'
import { ChartCardSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatCurrencyFull, formatMonthLabel } from '@/lib/format'
import type { RevenueTrendPoint } from '@/types/revenue'

interface ChartPoint {
  date: string
  label: string
  deal_revenue: number
  invoice_amount: number
  payments_received: number
}

/** These three columns are independent lifecycle stages -- won deal
 * revenue, billed amount, and cash collected -- never summed together
 * into one number (see docs/analytics_layer.md). Aggregating here only
 * collapses the region/segment grain the backend already SUMed the query
 * to, never mixes the three metrics into each other. */
function toChartPoints(points: RevenueTrendPoint[]): ChartPoint[] {
  const byPeriod = new Map<string, ChartPoint>()
  for (const p of points) {
    const key = p.period_start
    const existing = byPeriod.get(key)
    if (existing) {
      existing.deal_revenue += p.deal_revenue ?? 0
      existing.invoice_amount += p.invoice_amount ?? 0
      existing.payments_received += p.payments_received ?? 0
    } else {
      byPeriod.set(key, {
        date: key,
        label: p.period_label ?? formatMonthLabel(key),
        deal_revenue: p.deal_revenue ?? 0,
        invoice_amount: p.invoice_amount ?? 0,
        payments_received: p.payments_received ?? 0,
      })
    }
  }
  return Array.from(byPeriod.values()).sort((a, b) => a.date.localeCompare(b.date))
}

function ChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-popover">
      <p className="mb-1.5 font-medium text-slate-700">{label}</p>
      <div className="space-y-0.5">
        {payload.map((entry: any) => (
          <p key={entry.dataKey} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-slate-500">
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: entry.color }} />
              {entry.name}
            </span>
            <span className="font-medium text-slate-800">{formatCurrencyFull(entry.value)}</span>
          </p>
        ))}
      </div>
    </div>
  )
}

export function EnterpriseTrendChart() {
  const { filters } = useGlobalFilters()
  const state = useFetch(
    () => fetchRevenueTrends({ period: filters.period, region: filters.region || undefined, segment: filters.segment || undefined }),
    [filters.period, filters.region, filters.segment],
  )

  return (
    <ChartCard
      title="Enterprise Performance Trend"
      subtitle="Won-deal revenue, invoiced amount, and payments collected over time"
      className="col-span-full"
    >
      <AsyncContent
        state={state}
        skeleton={<ChartCardSkeleton height={340} />}
        isEmpty={(d) => d.points.length === 0}
        emptyMessage="No revenue data for the selected filters."
      >
        {(data) => {
          const points = toChartPoints(data.points)
          return (
            <ResponsiveContainer width="100%" height={340}>
              <AreaChart data={points} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                <defs>
                  <linearGradient id="revenueGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-brand-700)" stopOpacity={0.22} />
                    <stop offset="100%" stopColor="var(--color-brand-700)" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="invoiceGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-brand-500)" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="var(--color-brand-500)" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="paymentsGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="var(--color-teal-500)" stopOpacity={0.2} />
                    <stop offset="100%" stopColor="var(--color-teal-500)" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                <XAxis
                  dataKey="label"
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--color-border)' }}
                  minTickGap={24}
                />
                <YAxis
                  tickFormatter={(v) => formatCurrencyCompact(v)}
                  tick={{ fontSize: 11, fill: '#64748b' }}
                  tickLine={false}
                  axisLine={false}
                  width={72}
                />
                <Tooltip content={<ChartTooltip />} />
                <Area
                  type="monotone"
                  dataKey="deal_revenue"
                  name="Revenue (Won Deals)"
                  stroke="var(--color-brand-700)"
                  strokeWidth={2}
                  fill="url(#revenueGradient)"
                />
                <Area
                  type="monotone"
                  dataKey="invoice_amount"
                  name="Invoiced Amount"
                  stroke="var(--color-brand-500)"
                  strokeWidth={2}
                  fill="url(#invoiceGradient)"
                />
                <Area
                  type="monotone"
                  dataKey="payments_received"
                  name="Payments Collected"
                  stroke="var(--color-teal-600)"
                  strokeWidth={2}
                  fill="url(#paymentsGradient)"
                />
              </AreaChart>
            </ResponsiveContainer>
          )
        }}
      </AsyncContent>
    </ChartCard>
  )
}
