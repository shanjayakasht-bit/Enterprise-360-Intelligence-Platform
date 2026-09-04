import { apiClient } from './client'
import type { RevenueByRegionResponse, RevenueForecastResponse, RevenueTrendsResponse } from '@/types/revenue'

export interface RevenueTrendsParams {
  period?: string
  region?: string
  segment?: string
  service?: string
}

export async function fetchRevenueTrends(params: RevenueTrendsParams = {}): Promise<RevenueTrendsResponse> {
  const { data } = await apiClient.get<RevenueTrendsResponse>('/revenue/trends', { params })
  return data
}

export async function fetchRevenueForecast(): Promise<RevenueForecastResponse> {
  const { data } = await apiClient.get<RevenueForecastResponse>('/revenue/forecast')
  return data
}

export async function fetchRevenueByRegion(segment?: string): Promise<RevenueByRegionResponse> {
  const { data } = await apiClient.get<RevenueByRegionResponse>('/revenue/by-region', { params: { segment } })
  return data
}
