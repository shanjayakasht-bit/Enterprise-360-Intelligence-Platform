import { ArrowRight } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatCurrencyFull, formatDateTime } from '@/lib/format'
import type { DecisionCard } from '@/types/decision'
import { DrawerModal } from './DrawerModal'
import { RiskBadge } from './RiskBadge'

interface DecisionDetailDrawerProps {
  decision: DecisionCard | null
  onClose: () => void
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="mb-5">
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">{label}</p>
      <div className="text-sm leading-relaxed text-slate-700">{children}</div>
    </div>
  )
}

/** Only CUSTOMER and PROJECT decisions map onto a page this dashboard has
 * (Customer 360 / Projects) -- INVOICE/REGION/SERVICE/ENTERPRISE entities
 * have no dedicated detail route yet, so no link is shown for those. */
function entityLinkPath(entityType: string, entityId: string): string | null {
  if (entityType === 'CUSTOMER') return `/customers/${encodeURIComponent(entityId)}`
  if (entityType === 'PROJECT') return `/projects`
  return null
}

export function DecisionDetailDrawer({ decision, onClose }: DecisionDetailDrawerProps) {
  const linkPath = decision ? entityLinkPath(decision.entity_type, decision.entity_id) : null

  return (
    <DrawerModal open={decision !== null} onClose={onClose} title={decision?.title ?? ''}>
      {decision && (
        <div>
          <div className="mb-5 flex flex-wrap items-center gap-2">
            <RiskBadge level={decision.severity} />
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              {decision.decision_type.replace(/_/g, ' ')}
            </span>
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              Priority {decision.priority_score.toFixed(1)}
            </span>
            <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600">
              {decision.status}
            </span>
          </div>

          {decision.summary && <p className="mb-5 text-sm text-slate-600">{decision.summary}</p>}

          <Block label="What Happened">{decision.what_happened}</Block>

          <Block label="Contributing Signals">{decision.why_it_happened}</Block>

          <Block label="What May Happen">
            {decision.predicted_outcome ?? 'No model-backed prediction applies to this decision.'}
          </Block>

          <Block label="Business Impact">
            <div className="flex items-center gap-2">
              <span className="text-lg font-semibold text-slate-900">
                {decision.business_impact.value !== null ? formatCurrencyFull(decision.business_impact.value) : '—'}
              </span>
              {decision.business_impact.type && (
                <span className="text-xs text-slate-500">{decision.business_impact.type.replace(/_/g, ' ')}</span>
              )}
            </div>
          </Block>

          <Block label="Recommended Actions">
            <ol className="space-y-1.5">
              {decision.recommended_actions.map((action, i) => (
                <li key={i} className="flex gap-2 text-sm text-slate-700">
                  <span className="font-semibold text-brand-600">{i + 1}.</span>
                  {action}
                </li>
              ))}
            </ol>
          </Block>

          <Block label="Confidence">
            {decision.confidence !== null ? (
              <div className="flex items-center gap-2">
                <div className="h-1.5 w-32 overflow-hidden rounded-full bg-slate-100">
                  <div className="h-full rounded-full bg-brand-500" style={{ width: `${Math.min(decision.confidence, 100)}%` }} />
                </div>
                <span className="text-xs font-medium text-slate-600">{decision.confidence.toFixed(0)}%</span>
              </div>
            ) : (
              '—'
            )}
          </Block>

          <div className="flex items-center justify-between border-t border-border pt-3">
            <p className="text-[11px] text-slate-400">
              Entity: {decision.entity_type} {decision.entity_id} · Generated {formatDateTime(decision.generated_at)}
            </p>
            {linkPath && (
              <Link
                to={linkPath}
                onClick={onClose}
                className="inline-flex items-center gap-1 text-xs font-medium text-brand-600 hover:underline"
              >
                View {decision.entity_type === 'CUSTOMER' ? 'Customer' : 'Project'}
                <ArrowRight className="h-3.5 w-3.5" />
              </Link>
            )}
          </div>
        </div>
      )}
    </DrawerModal>
  )
}
