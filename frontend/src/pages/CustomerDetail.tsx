import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { fetchCustomerDetail } from '@/api/customers'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { RiskBadge } from '@/components/ui/RiskBadge'
import { SectionCard, DataRow } from '@/components/ui/SectionCard'
import { CardListSkeleton } from '@/components/ui/LoadingSkeleton'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyFull, formatDate, formatDateTime, formatFractionAsPercent, formatNumber } from '@/lib/format'

export function CustomerDetail() {
  const { customerId } = useParams<{ customerId: string }>()
  const navigate = useNavigate()
  const state = useFetch(() => fetchCustomerDetail(customerId!), [customerId])

  return (
    <AppLayout title="Customer 360" subtitle={customerId}>
      <button
        onClick={() => navigate('/customers')}
        className="mb-4 inline-flex items-center gap-1.5 text-xs font-medium text-slate-500 hover:text-slate-700"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        Back to Customers
      </button>

      <AsyncContent state={state} skeleton={<CardListSkeleton count={6} />}>
        {(data) => (
          <div className="space-y-6">
            <div className="rounded-xl border border-border bg-surface p-5 shadow-card">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-slate-900">{data.profile.company_name}</h2>
                  <p className="mt-0.5 text-sm text-slate-500">
                    {data.profile.industry ?? '—'} · {data.profile.region ?? '—'} · {data.profile.segment ?? '—'}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <RiskBadge level={data.risk_prediction.risk_level} />
                  <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
                    {data.profile.customer_status ?? 'Unknown'}
                  </span>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-6 md:grid-cols-2 xl:grid-cols-3">
              <SectionCard title="Profile">
                <DataRow label="Health Score" value={data.profile.customer_health_score?.toFixed(1) ?? '—'} />
                <DataRow label="Renewal Date" value={formatDate(data.profile.renewal_date)} />
                <DataRow label="Days to Renewal" value={data.profile.days_to_renewal ?? '—'} />
              </SectionCard>

              <SectionCard title="Revenue">
                <DataRow label="Total Deal Value" value={formatCurrencyFull(data.revenue.total_deal_value)} />
                <DataRow label="Won Deal Value" value={formatCurrencyFull(data.revenue.won_deal_value)} />
                <DataRow label="Total Revenue" value={formatCurrencyFull(data.revenue.total_revenue)} />
                <DataRow label="ARR" value={formatCurrencyFull(data.revenue.arr)} />
                <DataRow label="MRR" value={formatCurrencyFull(data.revenue.mrr)} />
              </SectionCard>

              <SectionCard title="Subscriptions">
                <DataRow label="Active Subscriptions" value={formatNumber(data.subscriptions.active_subscriptions)} />
                <DataRow label="ARR" value={formatCurrencyFull(data.subscriptions.arr)} />
                <DataRow label="MRR" value={formatCurrencyFull(data.subscriptions.mrr)} />
              </SectionCard>

              <SectionCard title="Projects">
                <DataRow label="Project Count" value={formatNumber(data.projects.project_count)} />
                <DataRow label="Delayed Projects" value={formatNumber(data.projects.delayed_projects)} />
                <DataRow label="Project Risk" value={data.projects.project_risk?.toFixed(1) ?? '—'} />
              </SectionCard>

              <SectionCard title="Finance">
                <DataRow label="Invoice Total" value={formatCurrencyFull(data.finance.invoice_total)} />
                <DataRow label="Payments Received" value={formatCurrencyFull(data.finance.payments_received)} />
                <DataRow label="Outstanding" value={formatCurrencyFull(data.finance.outstanding_amount)} />
                <DataRow
                  label="Avg. Payment Delay"
                  value={data.finance.average_payment_delay !== null ? `${data.finance.average_payment_delay.toFixed(1)} days` : '—'}
                />
              </SectionCard>

              <SectionCard title="Support">
                <DataRow label="Ticket Count" value={formatNumber(data.support.support_ticket_count)} />
                <DataRow label="Open Tickets" value={formatNumber(data.support.open_ticket_count)} />
                <DataRow label="SLA Breaches" value={formatNumber(data.support.sla_breaches)} />
                <DataRow
                  label="Avg. Satisfaction"
                  value={data.support.average_support_satisfaction?.toFixed(1) ?? '—'}
                />
              </SectionCard>

              <SectionCard title="Activity">
                <DataRow label="Activity Count" value={formatNumber(data.activity.activity_count)} />
                <DataRow label="Avg. Usage Score" value={data.activity.average_usage_score?.toFixed(1) ?? '—'} />
                <DataRow label="Recent Activity" value={formatDate(data.activity.recent_activity_date)} />
              </SectionCard>

              <SectionCard title="Segment">
                <DataRow label="Cluster" value={data.segment.cluster_segment_name ?? '—'} />
                <DataRow label="Churn Risk Category" value={data.segment.churn_risk_category ?? '—'} />
                <DataRow label="Churn Risk Score" value={data.segment.churn_risk_score?.toFixed(2) ?? '—'} />
              </SectionCard>

              <SectionCard title="Risk Prediction">
                <DataRow label="Risk Level" value={<RiskBadge level={data.risk_prediction.risk_level} />} />
                <DataRow label="Risk Probability" value={formatFractionAsPercent(data.risk_prediction.risk_probability)} />
                <DataRow label="Model Version" value={data.risk_prediction.model_version ?? '—'} />
              </SectionCard>
            </div>

            <SectionCard title="Active Decisions">
              {data.active_decisions.length === 0 ? (
                <p className="text-sm text-slate-500">No active decisions for this customer.</p>
              ) : (
                <div className="divide-y divide-border/70">
                  {data.active_decisions.map((d) => (
                    <div key={d.decision_id} className="flex items-center justify-between gap-4 py-2.5">
                      <div>
                        <p className="text-sm font-medium text-slate-800">{d.title}</p>
                        <p className="text-xs text-slate-400">{formatDateTime(d.generated_at)}</p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-medium text-slate-500">Priority {d.priority_score.toFixed(0)}</span>
                        <RiskBadge level={d.severity} />
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>
          </div>
        )}
      </AsyncContent>
    </AppLayout>
  )
}
