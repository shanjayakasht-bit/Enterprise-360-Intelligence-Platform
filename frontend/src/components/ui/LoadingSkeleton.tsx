interface LoadingSkeletonProps {
  className?: string
  style?: React.CSSProperties
}

/** A shimmering placeholder block -- used instead of plain "Loading..."
 * text everywhere a component is fetching data. */
export function LoadingSkeleton({ className = '', style }: LoadingSkeletonProps) {
  return <div className={`animate-pulse rounded-lg bg-slate-200/70 ${className}`} style={style} />
}

export function KpiCardSkeleton() {
  return (
    <div className="rounded-xl border border-border bg-surface p-5 shadow-card">
      <LoadingSkeleton className="mb-3 h-3.5 w-24" />
      <LoadingSkeleton className="mb-2 h-8 w-32" />
      <LoadingSkeleton className="h-3 w-20" />
    </div>
  )
}

export function ChartCardSkeleton({ height = 320 }: { height?: number }) {
  return (
    <div className="rounded-xl border border-border bg-surface p-5 shadow-card">
      <LoadingSkeleton className="mb-4 h-4 w-40" />
      <LoadingSkeleton style={{ height }} className="w-full" />
    </div>
  )
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <LoadingSkeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  )
}

export function CardListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="rounded-xl border border-border bg-surface p-4 shadow-card">
          <LoadingSkeleton className="mb-2 h-4 w-1/3" />
          <LoadingSkeleton className="mb-1 h-3 w-full" />
          <LoadingSkeleton className="h-3 w-2/3" />
        </div>
      ))}
    </div>
  )
}
