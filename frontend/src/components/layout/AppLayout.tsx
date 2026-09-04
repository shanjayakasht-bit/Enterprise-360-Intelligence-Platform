import type { ReactNode } from 'react'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

interface AppLayoutProps {
  title: string
  subtitle?: string
  children: ReactNode
}

export function AppLayout({ title, subtitle, children }: AppLayoutProps) {
  return (
    <div className="flex min-h-screen bg-canvas">
      <Sidebar />
      <div className="flex min-h-screen flex-1 flex-col">
        <Topbar title={title} subtitle={subtitle} />
        <main className="flex-1 px-6 py-6">
          <div className="mx-auto w-full max-w-[1600px]">{children}</div>
        </main>
      </div>
    </div>
  )
}
