import { AlertTriangle, RefreshCw } from 'lucide-react'
import type { NormalizedApiError } from '@/api/client'

interface ErrorStateProps {
  error: NormalizedApiError
  onRetry?: () => void
  compact?: boolean
}

export function ErrorState({ error, onRetry, compact = false }: ErrorStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 rounded-xl border border-severity-critical-border bg-severity-critical-bg text-center ${
        compact ? 'p-6' : 'p-12'
      }`}
    >
      <AlertTriangle className="h-6 w-6 text-severity-critical" />
      <div>
        <p className="text-sm font-medium text-slate-800">Could not load this data</p>
        <p className="mt-1 text-xs text-slate-500">{error.message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 inline-flex items-center gap-1.5 rounded-lg border border-border-strong bg-surface px-3 py-1.5 text-xs font-medium text-slate-700 shadow-card transition hover:bg-slate-50"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Retry
        </button>
      )}
    </div>
  )
}
