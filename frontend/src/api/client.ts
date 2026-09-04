import axios, { AxiosError } from 'axios'
import type { ApiErrorBody } from '@/types/common'

/** Base URL comes from VITE_API_BASE_URL (see .env.example) -- the
 * frontend never talks to Snowflake directly, only this one FastAPI base. */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined

if (!API_BASE_URL) {
  // Fails loudly in dev rather than silently hitting a wrong/undefined URL.
  // eslint-disable-next-line no-console
  console.error('VITE_API_BASE_URL is not set. Copy frontend/.env.example to frontend/.env')
}

export const apiClient = axios.create({
  baseURL: API_BASE_URL ?? 'http://127.0.0.1:8010/api/v1',
  timeout: 20000,
})

/** Normalized error shape every hook/component can rely on, regardless of
 * whether the failure was a network error, a validated API error body
 * ({"error": ..., "message": ...}, see backend/core/exceptions.py), or
 * something unexpected. */
export interface NormalizedApiError {
  status: number | null
  code: string
  message: string
}

export function normalizeApiError(err: unknown): NormalizedApiError {
  if (axios.isAxiosError(err)) {
    const axiosErr = err as AxiosError<ApiErrorBody>
    const status = axiosErr.response?.status ?? null
    const body = axiosErr.response?.data
    if (body?.error && body?.message) {
      return { status, code: body.error, message: body.message }
    }
    if (axiosErr.code === 'ECONNABORTED') {
      return { status, code: 'timeout', message: 'The request took too long to respond.' }
    }
    if (!axiosErr.response) {
      return { status, code: 'network_error', message: 'Could not reach the NEXORA API. Is the backend running?' }
    }
    return { status, code: 'unknown_error', message: axiosErr.message }
  }
  return { status: null, code: 'unknown_error', message: 'An unexpected error occurred.' }
}
