import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export interface GlobalFilters {
  period: string
  region: string
  segment: string
  department: string
  service: string
}

const DEFAULT_FILTERS: GlobalFilters = {
  period: 'monthly',
  region: '',
  segment: '',
  department: '',
  service: '',
}

interface FilterContextValue {
  filters: GlobalFilters
  setFilter: (key: keyof GlobalFilters, value: string) => void
  resetFilters: () => void
}

const FilterContext = createContext<FilterContextValue | null>(null)

/** Global topbar filters (Period/Region/Segment/Department/Service).
 * Individual pages read whichever of these their backend endpoint actually
 * supports (see docs/api_reference.md for the exact per-endpoint filter
 * list) -- a page never fabricates filtering behavior the API can't do. */
export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<GlobalFilters>(DEFAULT_FILTERS)

  const value = useMemo<FilterContextValue>(
    () => ({
      filters,
      setFilter: (key, val) => setFilters((prev) => ({ ...prev, [key]: val })),
      resetFilters: () => setFilters(DEFAULT_FILTERS),
    }),
    [filters],
  )

  return <FilterContext.Provider value={value}>{children}</FilterContext.Provider>
}

export function useGlobalFilters() {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useGlobalFilters must be used within FilterProvider')
  return ctx
}
