import { Link } from 'react-router-dom'
import { fetchProjectRisk } from '@/api/projects'
import { AsyncContent } from '@/components/ui/AsyncContent'
import { RiskBadge } from '@/components/ui/RiskBadge'
import { SectionCard, DataRow } from '@/components/ui/SectionCard'
import { TableSkeleton } from '@/components/ui/LoadingSkeleton'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'
import { formatPercent } from '@/lib/format'

export function ProjectRiskWidget() {
  const { filters } = useGlobalFilters()
  const state = useFetch(
    () => fetchProjectRisk({ page: 1, page_size: 5, risk_level: 'High', department: filters.department || undefined }),
    [filters.department],
  )

  return (
    <SectionCard title="Project Risk">
      <AsyncContent
        state={state}
        skeleton={<TableSkeleton rows={5} />}
        isEmpty={(d) => d.items.length === 0}
        emptyTitle="No high-risk projects"
        emptyMessage="All active projects are within normal risk thresholds."
      >
        {(data) => (
          <div>
            {data.items.map((project) => (
              <DataRow
                key={project.project_id}
                label={project.company_name}
                value={
                  <span className="flex items-center gap-2">
                    {project.completion_pct !== null && (
                      <span className="text-xs text-slate-400">{formatPercent(project.completion_pct, 0)} complete</span>
                    )}
                    <RiskBadge level={project.risk_level} />
                  </span>
                }
              />
            ))}
            <Link to="/projects" className="mt-3 inline-block text-xs font-medium text-brand-600 hover:underline">
              View all projects
            </Link>
          </div>
        )}
      </AsyncContent>
    </SectionCard>
  )
}
