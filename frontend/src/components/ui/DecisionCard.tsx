import { ArrowRight } from 'lucide-react'
import { formatCurrencyCompact } from '@/lib/format'
import type { DecisionCard as DecisionCardData } from '@/types/decision'
import { RiskBadge } from './RiskBadge'

interface DecisionCardProps {
  decision: DecisionCardData
  onView: (decision: DecisionCardData) => void
}

const ENTITY_LABEL: Record<string, string> = {
  CUSTOMER: 'Customer',
  PROJECT: 'Project',
  INVOICE: 'Invoice',
  REGION: 'Region',
  SERVICE: 'Service',
  ENTERPRISE: 'Enterprise',
}

export function DecisionCard({ decision, onView }: DecisionCardProps) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-card transition hover:shadow-card-hover">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <RiskBadge level={decision.severity} />
          <span className="text-xs text-slate-400">
            {ENTITY_LABEL[decision.entity_type] ?? decision.entity_type} · {decision.entity_id}
          </span>
        </div>
        <span className="whitespace-nowrap text-xs font-semibold text-slate-500">
          Priority {decision.priority_score.toFixed(0)}
        </span>
      </div>

      <h4 className="mt-2 text-sm font-semibold text-slate-900">{decision.title}</h4>
      {decision.summary && <p className="mt-1 line-clamp-2 text-xs text-slate-500">{decision.summary}</p>}

      <div className="mt-3 flex items-center justify-between border-t border-border/70 pt-3">
        <div className="text-xs">
          <span className="text-slate-400">Business impact </span>
          <span className="font-medium text-slate-700">
            {decision.business_impact.value !== null ? formatCurrencyCompact(decision.business_impact.value) : '—'}
          </span>
        </div>
        <button
          onClick={() => onView(decision)}
          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-brand-600 transition hover:bg-brand-50"
        >
          View Decision
          <ArrowRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  )
}
