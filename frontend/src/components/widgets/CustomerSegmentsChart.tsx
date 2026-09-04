import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { fetchCustomerSegmentSummary } from '@/api/customers'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { ChartCard } from '@/components/ui/ChartCard'
import { ChartCardSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatNumber, formatPercent } from '@/lib/format'

const SEGMENT_COLORS = [
  'var(--color-brand-500)',
  'var(--color-teal-500)',
  'var(--color-brand-300)',
  'var(--color-teal-300)',
  'var(--color-brand-700)',
  '#94a3b8',
]

function SegmentTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null
  const p = payload[0]
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2 text-xs shadow-popover">
      <p className="font-medium text-slate-700">{p.name}</p>
      <p className="text-slate-500">{formatNumber(p.value)} customers</p>
    </div>
  )
}

export function CustomerSegmentsChart() {
  const { filters } = useGlobalFilters()
  const state = useFetch(
    () => fetchCustomerSegmentSummary({ region: filters.region || undefined, segment: filters.segment || undefined }),
    [filters.region, filters.segment],
  )

  return (
    <ChartCard
      title="Customer Segments"
      subtitle={
        state.status === 'success'
          ? `Full population — ${formatNumber(state.data.total_customers)} customers, by ML cluster`
          : 'Full population, by ML-derived cluster segment'
      }
    >
      <AsyncContent
        state={state}
        skeleton={<ChartCardSkeleton height={260} />}
        isEmpty={(d) => d.segments.length === 0}
        emptyMessage="No customer segment data available for the current filters."
      >
        {(data) => (
          <div className="flex items-center gap-4">
            <ResponsiveContainer width="55%" height={220}>
              <PieChart>
                <Pie data={data.segments} dataKey="customer_count" nameKey="segment_name" innerRadius={55} outerRadius={90} paddingAngle={2}>
                  {data.segments.map((s, i) => (
                    <Cell key={s.segment_name} fill={SEGMENT_COLORS[i % SEGMENT_COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip content={<SegmentTooltip />} />
              </PieChart>
            </ResponsiveContainer>
            <ul className="flex-1 space-y-2">
              {data.segments.map((s, i) => (
                <li key={s.segment_name} className="flex items-center justify-between gap-2 text-xs">
                  <span className="flex items-center gap-1.5 text-slate-600">
                    <span className="h-2 w-2 shrink-0 rounded-full" style={{ backgroundColor: SEGMENT_COLORS[i % SEGMENT_COLORS.length] }} />
                    {s.segment_name}
                  </span>
                  <span className="whitespace-nowrap font-medium text-slate-800">
                    {formatNumber(s.customer_count)}{' '}
                    <span className="font-normal text-slate-400">
                      ({formatPercent((s.customer_count / data.total_customers) * 100, 0)})
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </AsyncContent>
    </ChartCard>
  )
}
