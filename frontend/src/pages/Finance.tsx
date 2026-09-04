import { useState } from 'react'
import { fetchOverview } from '@/api/overview'
import { fetchPaymentDelayPredictions } from '@/api/predictions'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { KpiCard } from '@/components/ui/KpiCard'
import { Pagination } from '@/components/ui/Pagination'
import { RiskBadge } from '@/components/ui/RiskBadge'
import { KpiCardSkeleton, TableSkeleton } from '@/components/ui/LoadingSkeleton'
import { EnterpriseTrendChart } from '@/components/widgets/EnterpriseTrendChart'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatFractionAsPercent } from '@/lib/format'
import { DollarSign, ReceiptText, Wallet } from 'lucide-react'

const PAGE_SIZE = 15

export function Finance() {
  const overviewState = useFetch(fetchOverview, [])
  const [page, setPage] = useState(1)
  const delayState = useFetch(() => fetchPaymentDelayPredictions({ page, page_size: PAGE_SIZE }), [page])

  return (
    <AppLayout title="Finance" subtitle="Invoicing, collections and payment-delay risk">
      <div className="space-y-6">
        <AsyncContent
          state={overviewState}
          skeleton={
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <KpiCardSkeleton key={i} />
              ))}
            </div>
          }
        >
          {(data) => (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <KpiCard label="Total Invoiced" value={formatCurrencyCompact(data.total_invoice_amount)} icon={ReceiptText} />
              <KpiCard label="Payments Received" value={formatCurrencyCompact(data.total_payments_received)} icon={DollarSign} />
              <KpiCard label="Outstanding" value={formatCurrencyCompact(data.outstanding_amount)} icon={Wallet} />
            </div>
          )}
        </AsyncContent>

        <EnterpriseTrendChart />

        <div className="rounded-xl border border-border bg-surface p-5 shadow-card">
          <h3 className="mb-4 text-sm font-semibold text-slate-900">Payment Delay Risk</h3>
          <AsyncContent
            state={delayState}
            skeleton={<TableSkeleton rows={8} />}
            isEmpty={(d) => d.items.length === 0}
            emptyMessage="No payment delay predictions available."
          >
            {(data) => (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
                        <th className="py-2 pr-4 font-medium">Invoice</th>
                        <th className="py-2 pr-4 font-medium">Customer</th>
                        <th className="py-2 pr-4 font-medium">Predicted Delay (days)</th>
                        <th className="py-2 pr-4 font-medium">Delay Probability</th>
                        <th className="py-2 font-medium">Risk</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.items.map((row) => (
                        <tr key={row.invoice_id} className="border-b border-border/70 last:border-b-0 hover:bg-canvas">
                          <td className="py-2.5 pr-4 font-medium text-slate-700">{row.invoice_id}</td>
                          <td className="py-2.5 pr-4 text-slate-600">{row.customer_id}</td>
                          <td className="py-2.5 pr-4 text-slate-700">{row.predicted_delay ?? '—'}</td>
                          <td className="py-2.5 pr-4 text-slate-700">{formatFractionAsPercent(row.delay_probability)}</td>
                          <td className="py-2.5">
                            <RiskBadge level={row.risk_level} />
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
      </div>
    </AppLayout>
  )
}
