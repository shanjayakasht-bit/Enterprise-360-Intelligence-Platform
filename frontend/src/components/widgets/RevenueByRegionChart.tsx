import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fetchRevenueByRegion } from '@/api/revenue'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { ChartCard } from '@/components/ui/ChartCard'
import { ChartCardSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatCurrencyFull } from '@/lib/format'

function RegionTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-popover">
      <p className="mb-1 font-medium text-slate-700">{label}</p>
      <p style={{ color: payload[0].color }}>Invoiced: {formatCurrencyFull(payload[0].value)}</p>
    </div>
  )
}

export function RevenueByRegionChart() {
  const { filters } = useGlobalFilters()
  const state = useFetch(() => fetchRevenueByRegion(filters.segment || undefined), [filters.segment])

  return (
    <ChartCard title="Revenue by Region" subtitle="All-time invoiced revenue by region">
      <AsyncContent
        state={state}
        skeleton={<ChartCardSkeleton height={260} />}
        isEmpty={(d) => d.rows.length === 0}
        emptyMessage="No regional revenue data available for the current filters."
      >
        {(data) => (
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={data.rows} layout="vertical" margin={{ top: 4, right: 24, left: 4, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" horizontal={false} />
              <XAxis
                type="number"
                dataKey="invoice_amount"
                tickFormatter={(v) => formatCurrencyCompact(v)}
                tick={{ fontSize: 11, fill: '#64748b' }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis type="category" dataKey="region_name" tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} width={100} />
              <Tooltip content={<RegionTooltip />} cursor={{ fill: 'var(--color-canvas)' }} />
              <Bar dataKey="invoice_amount" name="Invoiced Revenue" fill="var(--color-brand-500)" radius={[0, 4, 4, 0]} maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </AsyncContent>
    </ChartCard>
  )
}
