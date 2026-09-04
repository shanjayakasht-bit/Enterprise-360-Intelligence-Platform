import { useCallback, useEffect, useRef, useState } from 'react'
import { normalizeApiError, type NormalizedApiError } from '@/api/client'

export type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'error'; error: NormalizedApiError }
  | { status: 'success'; data: T }

/** Runs `fetcher` whenever `deps` changes, tracking loading/error/success
 * uniformly so every page/component handles the same four states the same
 * way (see components/ui/LoadingSkeleton, ErrorState, EmptyState).
 *
 * Guards against race conditions: if the deps change again before an
 * in-flight request resolves, the stale response is discarded rather than
 * overwriting a newer one. */
export function useFetch<T>(fetcher: () => Promise<T>, deps: React.DependencyList): AsyncState<T> & { refetch: () => void } {
  const [state, setState] = useState<AsyncState<T>>({ status: 'loading' })
  const requestIdRef = useRef(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const run = useCallback(() => {
    const requestId = ++requestIdRef.current
    setState({ status: 'loading' })
    fetcherRef
      .current()
      .then((data) => {
        if (requestIdRef.current === requestId) setState({ status: 'success', data })
      })
      .catch((err: unknown) => {
        if (requestIdRef.current === requestId) setState({ status: 'error', error: normalizeApiError(err) })
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  useEffect(() => {
    run()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)

  return { ...state, refetch: run }
}
