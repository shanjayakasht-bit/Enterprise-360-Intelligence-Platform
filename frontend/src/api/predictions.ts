import { apiClient } from './client'
import type { PaginatedResponse } from '@/types/common'
import type {
  CustomerRiskPredictionRow,
  PaymentDelayPredictionRow,
  ProjectRiskPredictionRow,
} from '@/types/prediction'
import type { RevenueForecastPoint } from '@/types/revenue'

export interface PredictionListParams {
  page?: number
  page_size?: number
  risk_level?: string
}

export async function fetchCustomerRiskPredictions(
  params: PredictionListParams,
): Promise<PaginatedResponse<CustomerRiskPredictionRow>> {
  const { data } = await apiClient.get<PaginatedResponse<CustomerRiskPredictionRow>>('/predictions/customers', {
    params,
  })
  return data
}

export async function fetchProjectRiskPredictions(
  params: PredictionListParams,
): Promise<PaginatedResponse<ProjectRiskPredictionRow>> {
  const { data } = await apiClient.get<PaginatedResponse<ProjectRiskPredictionRow>>('/predictions/projects', {
    params,
  })
  return data
}

export async function fetchPaymentDelayPredictions(
  params: PredictionListParams,
): Promise<PaginatedResponse<PaymentDelayPredictionRow>> {
  const { data } = await apiClient.get<PaginatedResponse<PaymentDelayPredictionRow>>('/predictions/payments', {
    params,
  })
  return data
}

export async function fetchRevenueForecastPredictions(): Promise<RevenueForecastPoint[]> {
  const { data } = await apiClient.get<RevenueForecastPoint[]>('/predictions/revenue')
  return data
}
