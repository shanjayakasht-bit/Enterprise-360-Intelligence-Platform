import { apiClient } from './client'
import type { PaginatedResponse } from '@/types/common'
import type { CustomerCard, CustomerDetail, CustomerSegmentSummaryResponse } from '@/types/customer'

export interface CustomerListParams {
  page?: number
  page_size?: number
  region?: string
  segment?: string
  risk_level?: string
  search?: string
}

export async function fetchCustomers(params: CustomerListParams): Promise<PaginatedResponse<CustomerCard>> {
  const { data } = await apiClient.get<PaginatedResponse<CustomerCard>>('/customers', { params })
  return data
}

export async function fetchCustomerDetail(customerId: string): Promise<CustomerDetail> {
  const { data } = await apiClient.get<CustomerDetail>(`/customers/${encodeURIComponent(customerId)}`)
  return data
}

export interface CustomerSegmentSummaryParams {
  region?: string
  segment?: string
  risk_level?: string
}

export async function fetchCustomerSegmentSummary(
  params: CustomerSegmentSummaryParams = {},
): Promise<CustomerSegmentSummaryResponse> {
  const { data } = await apiClient.get<CustomerSegmentSummaryResponse>('/customers/segments', { params })
  return data
}
