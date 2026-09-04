import { apiClient } from './client'
import type { OverviewResponse } from '@/types/overview'

export async function fetchOverview(): Promise<OverviewResponse> {
  const { data } = await apiClient.get<OverviewResponse>('/overview')
  return data
}
