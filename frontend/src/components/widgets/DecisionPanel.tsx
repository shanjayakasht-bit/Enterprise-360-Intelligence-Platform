import { useState } from 'react'
import { Link } from 'react-router-dom'
import { fetchDecisions, fetchDecisionSummary } from '@/api/decisions'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { DecisionCard } from '@/components/ui/DecisionCard'
import { DecisionDetailDrawer } from '@/components/ui/DecisionDetailDrawer'
import { CardListSkeleton, LoadingSkeleton } from '@/components/ui/LoadingSkeleton'
import { useFetch } from '@/hooks/useFetch'
import { formatCurrencyCompact, formatNumber } from '@/lib/format'
import type { DecisionCard as DecisionCardData } from '@/types/decision'

function SummaryStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex-1 rounded-lg border border-border/70 bg-canvas px-4 py-3">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-slate-900">{value}</p>
    </div>
  )
}

function DecisionSummaryStrip() {
  const state = useFetch(fetchDecisionSummary, [])

  return (
    <AsyncContent
      state={state}
      skeleton={
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <LoadingSkeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      }
    >
      {(data) => (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <SummaryStat label="Critical Decisions" value={formatNumber(data.critical_decisions)} />
          <SummaryStat label="High Priority" value={formatNumber(data.high_priority_decisions)} />
          <SummaryStat label="Customers at Risk" value={formatNumber(data.customers_at_risk)} />
          <SummaryStat label="Revenue at Risk" value={formatCurrencyCompact(data.revenue_at_risk)} />
        </div>
      )}
    </AsyncContent>
  )
}

export function DecisionPanel() {
  const [selected, setSelected] = useState<DecisionCardData | null>(null)
  const state = useFetch(() => fetchDecisions({ page: 1, page_size: 6 }), [])

  return (
    <div className="rounded-xl border border-border bg-surface p-5 shadow-card">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">Decision Engine</h3>
          <p className="mt-0.5 text-xs text-slate-500">Highest-priority decisions generated from live signals</p>
        </div>
        <Link to="/decisions" className="text-xs font-medium text-brand-600 hover:underline">
          View all decisions
        </Link>
      </div>

      <div className="mb-5">
        <DecisionSummaryStrip />
      </div>

      <AsyncContent
        state={state}
        skeleton={<CardListSkeleton count={4} />}
        isEmpty={(d) => d.items.length === 0}
        emptyTitle="No open decisions"
        emptyMessage="The decision engine has no active items for the current filters."
      >
        {(data) => (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {data.items.map((decision) => (
              <DecisionCard key={decision.decision_id} decision={decision} onView={setSelected} />
            ))}
          </div>
        )}
      </AsyncContent>

      <DecisionDetailDrawer decision={selected} onClose={() => setSelected(null)} />
    </div>
  )
}
