import { Link } from 'react-router-dom'
import { fetchCustomers } from '@/api/customers'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { ChartCard } from '@/components/ui/ChartCard'
import { RiskBadge } from '@/components/ui/RiskBadge'
import { TableSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatFractionAsPercent } from '@/lib/format'

export function AtRiskCustomersTable() {
  const { filters } = useGlobalFilters()
  const state = useFetch(
    () =>
      fetchCustomers({
        page: 1,
        page_size: 8,
        risk_level: 'High',
        region: filters.region || undefined,
        segment: filters.segment || undefined,
      }),
    [filters.region, filters.segment],
  )

  return (
    <ChartCard title="At-Risk Customers" subtitle="Highest churn-risk accounts, by ML risk score" className="col-span-full">
      <AsyncContent
        state={state}
        skeleton={<TableSkeleton rows={6} />}
        isEmpty={(d) => d.items.length === 0}
        emptyTitle="No high-risk customers"
        emptyMessage="No customers are currently flagged as high risk."
      >
        {(data) => (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Company</th>
                  <th className="py-2 pr-4 font-medium">Segment</th>
                  <th className="py-2 pr-4 font-medium">Region</th>
                  <th className="py-2 pr-4 font-medium">ARR</th>
                  <th className="py-2 pr-4 font-medium">Health</th>
                  <th className="py-2 pr-4 font-medium">Risk</th>
                  <th className="py-2 font-medium">Risk Probability</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((c) => (
                  <tr key={c.customer_id} className="border-b border-border/70 last:border-b-0 hover:bg-canvas">
                    <td className="py-2.5 pr-4">
                      <Link to={`/customers/${encodeURIComponent(c.customer_id)}`} className="font-medium text-brand-700 hover:underline">
                        {c.company_name}
                      </Link>
                    </td>
                    <td className="py-2.5 pr-4 text-slate-600">{c.segment ?? '—'}</td>
                    <td className="py-2.5 pr-4 text-slate-600">{c.region ?? '—'}</td>
                    <td className="py-2.5 pr-4 text-slate-700">{formatCurrencyCompact(c.arr)}</td>
                    <td className="py-2.5 pr-4 text-slate-700">
                      {c.customer_health_score !== null ? c.customer_health_score.toFixed(0) : '—'}
                    </td>
                    <td className="py-2.5 pr-4">
                      <RiskBadge level={c.risk_level} />
                    </td>
                    <td className="py-2.5 text-slate-700">{formatFractionAsPercent(c.risk_probability)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </AsyncContent>
    </ChartCard>
  )
}
