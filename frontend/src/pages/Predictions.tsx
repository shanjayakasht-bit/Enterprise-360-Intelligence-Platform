import { useState } from 'react'
import { fetchCustomerRiskPredictions, fetchPaymentDelayPredictions, fetchProjectRiskPredictions } from '@/api/predictions'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { Pagination } from '@/components/ui/Pagination'
import { RiskBadge } from '@/components/ui/RiskBadge'
import { ChartCard } from '@/components/ui/ChartCard'
import { TableSkeleton } from '@/components/ui/LoadingSkeleton'
import { useFetch } from '@/hooks/useFetch'
import { formatFractionAsPercent } from '@/lib/format'

const PAGE_SIZE = 10

function CustomerRiskTable() {
  const [page, setPage] = useState(1)
  const state = useFetch(() => fetchCustomerRiskPredictions({ page, page_size: PAGE_SIZE }), [page])

  return (
    <ChartCard title="Customer Churn Risk" subtitle="ML-predicted churn probability, not a certainty" className="col-span-full">
      <AsyncContent state={state} skeleton={<TableSkeleton rows={6} />} isEmpty={(d) => d.items.length === 0} emptyMessage="No predictions available.">
        {(data) => (
          <>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Customer</th>
                  <th className="py-2 pr-4 font-medium">Risk Probability</th>
                  <th className="py-2 pr-4 font-medium">Risk Level</th>
                  <th className="py-2 font-medium">Model</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.customer_id} className="border-b border-border/70 last:border-b-0 hover:bg-canvas">
                    <td className="py-2.5 pr-4 font-medium text-slate-700">{row.customer_id}</td>
                    <td className="py-2.5 pr-4 text-slate-700">{formatFractionAsPercent(row.risk_probability)}</td>
                    <td className="py-2.5 pr-4">
                      <RiskBadge level={row.risk_level} />
                    </td>
                    <td className="py-2.5 text-slate-500">{row.model_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination pageInfo={data.page_info} onPageChange={setPage} />
          </>
        )}
      </AsyncContent>
    </ChartCard>
  )
}

function ProjectRiskTable() {
  const [page, setPage] = useState(1)
  const state = useFetch(() => fetchProjectRiskPredictions({ page, page_size: PAGE_SIZE }), [page])

  return (
    <ChartCard title="Project Delivery Risk" subtitle="ML-predicted risk of delay or overrun, not a certainty" className="col-span-full">
      <AsyncContent state={state} skeleton={<TableSkeleton rows={6} />} isEmpty={(d) => d.items.length === 0} emptyMessage="No predictions available.">
        {(data) => (
          <>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Project</th>
                  <th className="py-2 pr-4 font-medium">Risk Probability</th>
                  <th className="py-2 pr-4 font-medium">Risk Level</th>
                  <th className="py-2 font-medium">Model</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.project_id} className="border-b border-border/70 last:border-b-0 hover:bg-canvas">
                    <td className="py-2.5 pr-4 font-medium text-slate-700">{row.project_id}</td>
                    <td className="py-2.5 pr-4 text-slate-700">{formatFractionAsPercent(row.risk_probability)}</td>
                    <td className="py-2.5 pr-4">
                      <RiskBadge level={row.risk_level} />
                    </td>
                    <td className="py-2.5 text-slate-500">{row.model_version}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination pageInfo={data.page_info} onPageChange={setPage} />
          </>
        )}
      </AsyncContent>
    </ChartCard>
  )
}

function PaymentDelayTable() {
  const [page, setPage] = useState(1)
  const state = useFetch(() => fetchPaymentDelayPredictions({ page, page_size: PAGE_SIZE }), [page])

  return (
    <ChartCard title="Payment Delay Risk" subtitle="ML-predicted invoice payment delay, not a certainty" className="col-span-full">
      <AsyncContent state={state} skeleton={<TableSkeleton rows={6} />} isEmpty={(d) => d.items.length === 0} emptyMessage="No predictions available.">
        {(data) => (
          <>
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-slate-400">
                  <th className="py-2 pr-4 font-medium">Invoice</th>
                  <th className="py-2 pr-4 font-medium">Customer</th>
                  <th className="py-2 pr-4 font-medium">Delay Probability</th>
                  <th className="py-2 font-medium">Risk Level</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.invoice_id} className="border-b border-border/70 last:border-b-0 hover:bg-canvas">
                    <td className="py-2.5 pr-4 font-medium text-slate-700">{row.invoice_id}</td>
                    <td className="py-2.5 pr-4 text-slate-600">{row.customer_id}</td>
                    <td className="py-2.5 pr-4 text-slate-700">{formatFractionAsPercent(row.delay_probability)}</td>
                    <td className="py-2.5">
                      <RiskBadge level={row.risk_level} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pagination pageInfo={data.page_info} onPageChange={setPage} />
          </>
        )}
      </AsyncContent>
    </ChartCard>
  )
}

export function Predictions() {
  return (
    <AppLayout title="Predictions" subtitle="Model-generated forecasts across customers, projects and payments — predictions, not guarantees">
      <div className="space-y-6">
        <CustomerRiskTable />
        <ProjectRiskTable />
        <PaymentDelayTable />
      </div>
    </AppLayout>
  )
}
