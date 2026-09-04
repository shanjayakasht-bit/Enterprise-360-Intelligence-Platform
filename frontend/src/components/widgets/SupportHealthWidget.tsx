import { fetchSupportMetrics } from '@/api/support'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { SectionCard, DataRow } from '@/components/ui/SectionCard'
import { LoadingSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatNumber } from '@/lib/format'

export function SupportHealthWidget() {
  const { filters } = useGlobalFilters()
  const state = useFetch(() => fetchSupportMetrics({ region: filters.region || undefined }), [filters.region])

  return (
    <SectionCard title="Support Health">
      <AsyncContent
        state={state}
        skeleton={
          <div className="space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <LoadingSkeleton key={i} className="h-8 w-full" />
            ))}
          </div>
        }
      >
        {(data) => (
          <div>
            <DataRow label="Total Tickets" value={formatNumber(data.total_tickets)} />
            <DataRow label="Open Tickets" value={formatNumber(data.open_tickets)} />
            <DataRow label="High Priority" value={formatNumber(data.high_priority_tickets)} />
            <DataRow label="SLA Breaches" value={formatNumber(data.sla_breaches)} />
            <DataRow
              label="Avg. Satisfaction"
              value={data.avg_satisfaction_rating !== null ? data.avg_satisfaction_rating.toFixed(1) : '—'}
            />
            <DataRow
              label="Avg. Resolution Time"
              value={data.avg_resolution_time_hours !== null ? `${data.avg_resolution_time_hours.toFixed(1)}h` : '—'}
            />
          </div>
        )}
      </AsyncContent>
    </SectionCard>
  )
}
