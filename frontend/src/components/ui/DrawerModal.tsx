import { X } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'

interface DrawerModalProps {
  open: boolean
  onClose: () => void
  title: string
  children: ReactNode
}

export function DrawerModal({ open, onClose, title, children }: DrawerModalProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-slate-900/30" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-xl flex-col bg-surface shadow-popover">
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <h2 className="text-base font-semibold text-slate-900">{title}</h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1.5 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="scrollbar-thin flex-1 overflow-y-auto px-6 py-5">{children}</div>
      </div>
    </div>
  )
}
