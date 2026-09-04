import type { ReactNode } from 'react'

interface ChartCardProps {
  title: string
  subtitle?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

export function ChartCard({ title, subtitle, action, children, className = '' }: ChartCardProps) {
  return (
    <div className={`rounded-xl border border-border bg-surface p-5 shadow-card ${className}`}>
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
          {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
        </div>
        {action}
      </div>
      {children}
    </div>
  )
}
