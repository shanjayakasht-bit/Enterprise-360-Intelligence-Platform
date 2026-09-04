import {
  Boxes,
  Gauge,
  LayoutGrid,
  LifeBuoy,
  Settings,
  Sparkles,
  Users,
  Wallet,
  Zap,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', icon: LayoutGrid, end: true },
  { to: '/customers', label: 'Customers', icon: Users },
  { to: '/revenue', label: 'Revenue', icon: Gauge },
  { to: '/projects', label: 'Projects', icon: Boxes },
  { to: '/finance', label: 'Finance', icon: Wallet },
  { to: '/support', label: 'Support', icon: LifeBuoy },
  { to: '/predictions', label: 'Predictions', icon: Sparkles },
  { to: '/decisions', label: 'Decisions', icon: Zap },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  return (
    <aside className="flex h-screen w-60 shrink-0 flex-col border-r border-border bg-surface">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
          N
        </div>
        <div>
          <p className="text-sm font-semibold leading-tight text-slate-900">NEXORA</p>
          <p className="text-[11px] leading-tight text-slate-500">Decision Intelligence</p>
        </div>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-2">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
                isActive
                  ? 'bg-brand-50 text-brand-700'
                  : 'text-slate-600 hover:bg-slate-50 hover:text-slate-900'
              }`
            }
          >
            <Icon className="h-4 w-4" />
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-border px-4 py-3">
        <p className="text-[11px] text-slate-400">NEXORA API v1.0.0</p>
      </div>
    </aside>
  )
}
