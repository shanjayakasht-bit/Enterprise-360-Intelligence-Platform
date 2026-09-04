import { Inbox, type LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  title?: string
  message?: string
  icon?: LucideIcon
}

export function EmptyState({ title = 'No data', message = 'Nothing matches the current filters.', icon: Icon = Inbox }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-dashed border-border-strong bg-canvas p-12 text-center">
      <Icon className="h-6 w-6 text-slate-400" />
      <p className="text-sm font-medium text-slate-700">{title}</p>
      <p className="text-xs text-slate-500">{message}</p>
    </div>
  )
}
