import { Bell, UserCircle } from 'lucide-react'
import { FilterBar } from './FilterBar'

interface TopbarProps {
  title: string
  subtitle?: string
}

export function Topbar({ title, subtitle }: TopbarProps) {
  return (
    <header className="sticky top-0 z-10 border-b border-border bg-surface/95 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-4 px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold text-slate-900">{title}</h1>
          {subtitle && <p className="text-xs text-slate-500">{subtitle}</p>}
        </div>

        <div className="flex items-center gap-4">
          <FilterBar />
          <div className="flex items-center gap-2 border-l border-border pl-4">
            <button
              aria-label="Notifications"
              className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
            >
              <Bell className="h-4 w-4" />
            </button>
            <button
              aria-label="Profile"
              className="rounded-lg p-1 text-slate-500 transition hover:bg-slate-50 hover:text-slate-700"
            >
              <UserCircle className="h-7 w-7" />
            </button>
          </div>
        </div>
      </div>
    </header>
  )
}
