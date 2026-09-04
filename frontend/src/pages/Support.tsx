import { AlertCircle, Clock, MessageSquare, Smile, TicketCheck } from 'lucide-react'
import { fetchSupportMetrics } from '@/api/support'
import { AppLayout } from '@/components/layout/AppLayout'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { KpiCard } from '@/components/ui/KpiCard'
import { KpiCardSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatNumber } from '@/lib/format'

export function Support() {
  const { filters } = useGlobalFilters()
  const state = useFetch(() => fetchSupportMetrics({ region: filters.region || undefined }), [filters.region])

  return (
    <AppLayout title="Support" subtitle="Ticket volume, SLA performance and satisfaction">
      <AsyncContent
        state={state}
        skeleton={
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            {Array.from({ length: 5 }).map((_, i) => (
              <KpiCardSkeleton key={i} />
            ))}
          </div>
        }
      >
        {(data) => (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <KpiCard label="Total Tickets" value={formatNumber(data.total_tickets)} icon={MessageSquare} />
            <KpiCard label="Open Tickets" value={formatNumber(data.open_tickets)} icon={TicketCheck} />
            <KpiCard label="High Priority" value={formatNumber(data.high_priority_tickets)} icon={AlertCircle} />
            <KpiCard label="SLA Breaches" value={formatNumber(data.sla_breaches)} icon={Clock} />
            <KpiCard
              label="Avg. Satisfaction"
              value={data.avg_satisfaction_rating !== null ? data.avg_satisfaction_rating.toFixed(1) : '—'}
              icon={Smile}
            />
          </div>
        )}
      </AsyncContent>
    </AppLayout>
  )
}
