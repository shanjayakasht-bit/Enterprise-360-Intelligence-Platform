import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { fetchCustomers } from '@/api/customers'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { Pagination } from '@/components/ui/Pagination'
import { RiskBadge } from '@/components/ui/RiskBadge'
import { TableSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatFractionAsPercent } from '@/lib/format'

const PAGE_SIZE = 20

export function Customers() {
  const { filters } = useGlobalFilters()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')

  const state = useFetch(
    () =>
      fetchCustomers({
        page,
        page_size: PAGE_SIZE,
        region: filters.region || undefined,
        segment: filters.segment || undefined,
        search: search || undefined,
      }),
    [page, filters.region, filters.segment, search],
  )

  return (
    <AppLayout title="Customers" subtitle="Full customer base with health and risk signals">
      <div className="space-y-4">
        <div className="flex items-center gap-2">
          <div className="relative w-72">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              placeholder="Search company name..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value)
                setPage(1)
              }}
              className="w-full rounded-lg border border-border bg-surface py-1.5 pl-8 pr-3 text-sm text-slate-700 outline-none focus:border-brand-500"
            />
          </div>
        </div>

        <div className="rounded-xl border border-border bg-surface p-5 shadow-card">
          <AsyncContent
            state={state}
            skeleton={<TableSkeleton rows={10} />}
            isEmpty={(d) => d.items.length === 0}
            emptyMessage="No customers match the current filters."
          >
            {(data) => (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
                        <th className="py-2 pr-4 font-medium">Company</th>
                        <th className="py-2 pr-4 font-medium">Segment</th>
                        <th className="py-2 pr-4 font-medium">Region</th>
                        <th className="py-2 pr-4 font-medium">Industry</th>
                        <th className="py-2 pr-4 font-medium">ARR</th>
                        <th className="py-2 pr-4 font-medium">Health</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                        <th className="py-2 pr-4 font-medium">Risk</th>
                        <th className="py-2 font-medium">Risk Probability</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((c) => (
                        <tr key={c.customer_id} className="border-b border-border/70 last:border-b-0 hover:bg-canvas">
                          <td className="py-2.5 pr-4">
                            <Link
                              to={`/customers/${encodeURIComponent(c.customer_id)}`}
                              className="font-medium text-brand-700 hover:underline"
                            >
                              {c.company_name}
                            </Link>
                          </td>
                          <td className="py-2.5 pr-4 text-slate-600">{c.segment ?? '—'}</td>
                          <td className="py-2.5 pr-4 text-slate-600">{c.region ?? '—'}</td>
                          <td className="py-2.5 pr-4 text-slate-600">{c.industry ?? '—'}</td>
                          <td className="py-2.5 pr-4 text-slate-700">{formatCurrencyCompact(c.arr)}</td>
                          <td className="py-2.5 pr-4 text-slate-700">
                            {c.customer_health_score !== null ? c.customer_health_score.toFixed(0) : '—'}
                          </td>
                          <td className="py-2.5 pr-4 text-slate-600">{c.customer_status ?? '—'}</td>
                          <td className="py-2.5 pr-4">
                            <RiskBadge level={c.risk_level} />
                          </td>
                          <td className="py-2.5 text-slate-700">{formatFractionAsPercent(c.risk_probability)}</td>
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
      </div>
    </AppLayout>
  )
}
