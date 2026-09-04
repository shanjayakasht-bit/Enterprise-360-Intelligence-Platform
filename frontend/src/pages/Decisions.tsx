import { useMemo, useState } from 'react'
import { fetchDecisions } from '@/api/decisions'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { DecisionCard } from '@/components/ui/DecisionCard'
import { DecisionDetailDrawer } from '@/components/ui/DecisionDetailDrawer'
import { Pagination } from '@/components/ui/Pagination'
import { CardListSkeleton } from '@/components/ui/LoadingSkeleton'
import { useFetch } from '@/hooks/useFetch'
import type { DecisionCard as DecisionCardData } from '@/types/decision'

const PAGE_SIZE = 12
const SEVERITIES = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const DECISION_TYPES = ['CUSTOMER_RETENTION', 'PROJECT_DELIVERY', 'PAYMENT_COLLECTION', 'REVENUE_OPPORTUNITY', 'BUSINESS_ANOMALY']
const STATUSES = ['NEW', 'ACKNOWLEDGED', 'IN_PROGRESS', 'RESOLVED', 'DISMISSED']

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: string[]
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-slate-600 outline-none focus:border-brand-500"
    >
      <option value="">All {label}</option>
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt.replace(/_/g, ' ')}
        </option>
      ))}
    </select>
  )
}

export function Decisions() {
  const [severity, setSeverity] = useState('')
  const [decisionType, setDecisionType] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState<DecisionCardData | null>(null)

  const state = useFetch(
    () =>
      fetchDecisions({
        page,
        page_size: PAGE_SIZE,
        severity: severity || undefined,
        decision_type: decisionType || undefined,
        status: status || undefined,
      }),
    [page, severity, decisionType, status],
  )

  const sortedItems = useMemo(() => {
    if (state.status !== 'success') return []
    return [...state.data.items].sort((a, b) => b.priority_score - a.priority_score)
  }, [state])

  return (
    <AppLayout title="Decisions" subtitle="All active decisions, ranked by priority">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <FilterSelect label="Severities" value={severity} onChange={(v) => { setSeverity(v); setPage(1) }} options={SEVERITIES} />
        <FilterSelect label="Types" value={decisionType} onChange={(v) => { setDecisionType(v); setPage(1) }} options={DECISION_TYPES} />
        <FilterSelect label="Statuses" value={status} onChange={(v) => { setStatus(v); setPage(1) }} options={STATUSES} />
      </div>

      <AsyncContent
        state={state}
        skeleton={<CardListSkeleton count={6} />}
        isEmpty={(d) => d.items.length === 0}
        emptyTitle="No decisions found"
        emptyMessage="No decisions match the current filters."
      >
        {(data) => (
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {sortedItems.map((decision) => (
                <DecisionCard key={decision.decision_id} decision={decision} onView={setSelected} />
              ))}
            </div>
            <Pagination pageInfo={data.page_info} onPageChange={setPage} />
          </div>
        )}
      </AsyncContent>

      <DecisionDetailDrawer decision={selected} onClose={() => setSelected(null)} />
    </AppLayout>
  )
}
