import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

interface SectionCardProps {
  title: string
  icon?: LucideIcon
  children: ReactNode
  className?: string
}

/** Used for the Customer 360 / Project detail section grid (Profile,
 * Revenue, Subscriptions, ...). */
export function SectionCard({ title, icon: Icon, children, className = '' }: SectionCardProps) {
  return (
    <div className={`rounded-xl border border-border bg-surface p-5 shadow-card ${className}`}>
      <div className="mb-3 flex items-center gap-2">
        {Icon && <Icon className="h-4 w-4 text-brand-600" />}
        <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      </div>
      {children}
    </div>
  )
}

export function DataRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-border/70 py-2 text-sm last:border-b-0">
      <span className="text-slate-500">{label}</span>
      <span className="font-medium text-slate-800">{value}</span>
    </div>
  )
}
