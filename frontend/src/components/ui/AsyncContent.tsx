import type { ReactNode } from 'react'
import type { AsyncState } from '@/hooks/useFetch'
import { EmptyState } from './EmptyState'
import { ErrorState } from './ErrorState'

interface AsyncContentProps<T> {
  state: AsyncState<T> & { refetch: () => void }
  skeleton: ReactNode
  isEmpty?: (data: T) => boolean
  emptyTitle?: string
  emptyMessage?: string
  children: (data: T) => ReactNode
}

/** The single place every page/widget routes its useFetch() result through
 * -- guarantees the same loading/error/empty/success treatment everywhere
 * instead of each component reinventing it. */
export function AsyncContent<T>({ state, skeleton, isEmpty, emptyTitle, emptyMessage, children }: AsyncContentProps<T>) {
  if (state.status === 'loading') return <>{skeleton}</>
  if (state.status === 'error') return <ErrorState error={state.error} onRetry={state.refetch} />
  if (isEmpty?.(state.data)) return <EmptyState title={emptyTitle} message={emptyMessage} />
  return <>{children(state.data)}</>
}
