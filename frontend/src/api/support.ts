import { apiClient } from './client'
import type { SupportMetricsResponse } from '@/types/support'

export interface SupportMetricsParams {
  priority?: string
  status?: string
  customer_id?: string
  region?: string
}

export async function fetchSupportMetrics(params: SupportMetricsParams = {}): Promise<SupportMetricsResponse> {
  const { data } = await apiClient.get<SupportMetricsResponse>('/support', { params })
  return data
}
