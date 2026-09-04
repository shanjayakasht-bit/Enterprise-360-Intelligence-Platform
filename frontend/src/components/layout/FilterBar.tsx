import { fetchDepartments, fetchRegions, fetchSegments, fetchServices } from '@/api/metadata'
import { useGlobalFilters } from '@/context/FilterContext'
import { useFetch } from '@/hooks/useFetch'

const PERIOD_OPTIONS = [
  { value: 'daily', label: 'Daily' },
  { value: 'monthly', label: 'Monthly' },
  { value: 'quarterly', label: 'Quarterly' },
  { value: 'yearly', label: 'Yearly' },
]

function Select({
  value,
  onChange,
  options,
  placeholder,
}: {
  value: string
  onChange: (v: string) => void
  options: string[]
  placeholder: string
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-xs font-medium text-slate-700 shadow-sm outline-none transition focus:border-brand-400 focus:ring-1 focus:ring-brand-400"
    >
      <option value="">{placeholder}</option>
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  )
}

/** Global filters shown in the topbar. Wired to whichever page-level
 * queries actually support them (see docs/api_reference.md) -- values are
 * fetched live from /api/v1/metadata/*, never hardcoded. */
export function FilterBar() {
  const { filters, setFilter } = useGlobalFilters()
  const regions = useFetch(fetchRegions, [])
  const segments = useFetch(fetchSegments, [])
  const departments = useFetch(fetchDepartments, [])
  const services = useFetch(fetchServices, [])

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={filters.period}
        onChange={(v) => setFilter('period', v)}
        options={PERIOD_OPTIONS.map((p) => p.value)}
        placeholder="Period"
      />
      <Select
        value={filters.region}
        onChange={(v) => setFilter('region', v)}
        options={regions.status === 'success' ? regions.data : []}
        placeholder="All Regions"
      />
      <Select
        value={filters.segment}
        onChange={(v) => setFilter('segment', v)}
        options={segments.status === 'success' ? segments.data : []}
        placeholder="All Segments"
      />
      <Select
        value={filters.department}
        onChange={(v) => setFilter('department', v)}
        options={departments.status === 'success' ? departments.data : []}
        placeholder="All Departments"
      />
      <Select
        value={filters.service}
        onChange={(v) => setFilter('service', v)}
        options={services.status === 'success' ? services.data.map((s) => s.service_name) : []}
        placeholder="All Services"
      />
    </div>
  )
}
