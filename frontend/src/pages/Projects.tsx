import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchProjectRisk } from '@/api/projects'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { Pagination } from '@/components/ui/Pagination'
import { RiskBadge } from '@/components/ui/RiskBadge'
import { TableSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatPercent } from '@/lib/format'

const PAGE_SIZE = 20

export function Projects() {
  const { filters } = useGlobalFilters()
  const [page, setPage] = useState(1)

  const state = useFetch(
    () => fetchProjectRisk({ page, page_size: PAGE_SIZE, department: filters.department || undefined }),
    [page, filters.department],
  )

  return (
    <AppLayout title="Projects" subtitle="Delivery risk across all active engagements">
      <div className="rounded-xl border border-border bg-surface p-5 shadow-card">
        <AsyncContent
          state={state}
          skeleton={<TableSkeleton rows={10} />}
          isEmpty={(d) => d.items.length === 0}
          emptyMessage="No projects match the current filters."
        >
          {(data) => (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
                      <th className="py-2 pr-4 font-medium">Customer</th>
                      <th className="py-2 pr-4 font-medium">Department</th>
                      <th className="py-2 pr-4 font-medium">Manager</th>
                      <th className="py-2 pr-4 font-medium">Status</th>
                      <th className="py-2 pr-4 font-medium">Budget</th>
                      <th className="py-2 pr-4 font-medium">Completion</th>
                      <th className="py-2 pr-4 font-medium">Days to Deadline</th>
                      <th className="py-2 font-medium">Risk</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.items.map((p) => (
                      <tr key={p.project_id} className="border-b border-border/70 last:border-b-0 hover:bg-canvas">
                        <td className="py-2.5 pr-4">
                          <Link to={`/customers/${encodeURIComponent(p.customer_id)}`} className="font-medium text-brand-700 hover:underline">
                            {p.company_name}
                          </Link>
                        </td>
                        <td className="py-2.5 pr-4 text-slate-600">{p.department_name ?? '—'}</td>
                        <td className="py-2.5 pr-4 text-slate-600">{p.project_manager_name ?? '—'}</td>
                        <td className="py-2.5 pr-4 text-slate-600">{p.status}</td>
                        <td className="py-2.5 pr-4 text-slate-700">{formatCurrencyCompact(p.budget)}</td>
                        <td className="py-2.5 pr-4 text-slate-700">{formatPercent(p.completion_pct, 0)}</td>
                        <td className="py-2.5 pr-4 text-slate-700">{p.days_to_deadline ?? '—'}</td>
                        <td className="py-2.5">
                          <RiskBadge level={p.risk_level} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination pageInfo={data.page_info} onPageChange={setPage} />
            </>
          )}
        </AsyncContent>
      </div>
    </AppLayout>
  )
}
