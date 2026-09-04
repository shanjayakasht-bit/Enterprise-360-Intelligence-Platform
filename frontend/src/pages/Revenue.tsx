import { Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { fetchRevenueForecast } from '@/api/revenue'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { ChartCard } from '@/components/ui/ChartCard'
import { ChartCardSkeleton } from '@/components/ui/LoadingSkeleton'
import { EnterpriseTrendChart } from '@/components/widgets/EnterpriseTrendChart'
import { RevenueByRegionChart } from '@/components/widgets/RevenueByRegionChart'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatCurrencyFull, formatDate, formatMonthLabel } from '@/lib/format'

interface CombinedPoint {
  label: string
  historical: number | null
  forecast: number | null
  lower_bound: number | null
  upper_bound: number | null
}

function ForecastTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-popover">
      <p className="mb-1 font-medium text-slate-700">{label}</p>
      {payload.map((entry: any) =>
        entry.value === null || entry.value === undefined ? null : (
          <p key={entry.dataKey} style={{ color: entry.color }}>
            {entry.name}: {formatCurrencyFull(entry.value)}
          </p>
        ),
      )}
    </div>
  )
}

export function Revenue() {
  const state = useFetch(fetchRevenueForecast, [])

  return (
    <AppLayout title="Revenue" subtitle="Historical performance and model-generated forecast">
      <div className="space-y-6">
        <EnterpriseTrendChart />

        <ChartCard
          title="Invoiced Revenue Forecast"
          subtitle="Solid line is historical invoiced amount; dashed line and shaded band are the model's predicted invoiced amount, not a guarantee"
          className="col-span-full"
        >
          <AsyncContent
            state={state}
            skeleton={<ChartCardSkeleton height={340} />}
            isEmpty={(d) => d.historical_context.length === 0 && d.forecast.length === 0}
            emptyMessage="No forecast data available yet."
          >
            {(data) => {
              const points: CombinedPoint[] = [
                ...data.historical_context.map((h) => ({
                  label: formatMonthLabel(h.month),
                  historical: h.invoice_amount,
                  forecast: null,
                  lower_bound: null,
                  upper_bound: null,
                })),
                ...data.forecast.map((f) => ({
                  label: formatDate(f.forecast_date),
                  historical: null,
                  forecast: f.predicted_revenue,
                  lower_bound: f.lower_bound,
                  upper_bound: f.upper_bound,
                })),
              ]
              return (
                <>
                  <ResponsiveContainer width="100%" height={340}>
                    <ComposedChart data={points} margin={{ top: 8, right: 12, left: 4, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                      <XAxis dataKey="label" tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={{ stroke: 'var(--color-border)' }} minTickGap={20} />
                      <YAxis tickFormatter={(v) => formatCurrencyCompact(v)} tick={{ fontSize: 11, fill: '#64748b' }} tickLine={false} axisLine={false} width={72} />
                      <Tooltip content={<ForecastTooltip />} />
                      <Area
                        dataKey="upper_bound"
                        name="Upper Bound"
                        stroke="none"
                        fill="var(--color-teal-500)"
                        fillOpacity={0.1}
                      />
                      <Area
                        dataKey="lower_bound"
                        name="Lower Bound"
                        stroke="none"
                        fill="var(--color-surface)"
                        fillOpacity={1}
                      />
                      <Line type="monotone" dataKey="historical" name="Historical Invoiced Amount" stroke="var(--color-brand-600)" strokeWidth={2} dot={false} connectNulls={false} />
                      <Line
                        type="monotone"
                        dataKey="forecast"
                        name="Forecasted Invoiced Amount"
                        stroke="var(--color-teal-600)"
                        strokeWidth={2}
                        strokeDasharray="5 4"
                        dot={false}
                        connectNulls={false}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                  <p className="mt-3 text-xs text-slate-400">
                    Forecast values are model predictions and are not guaranteed outcomes.
                  </p>
                </>
              )
            }}
          </AsyncContent>
        </ChartCard>

        <RevenueByRegionChart />
      </div>
    </AppLayout>
  )
}
