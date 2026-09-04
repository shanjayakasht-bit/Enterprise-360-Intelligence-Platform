import { apiClient } from './client'
import type { PaginatedResponse } from '@/types/common'
import type { DecisionCard, DecisionSummaryResponse } from '@/types/decision'

export interface DecisionListParams {
  page?: number
  page_size?: number
  severity?: string
  decision_type?: string
  entity_type?: string
  status?: string
}

export async function fetchDecisions(params: DecisionListParams): Promise<PaginatedResponse<DecisionCard>> {
  const { data } = await apiClient.get<PaginatedResponse<DecisionCard>>('/decisions', { params })
  return data
}

export async function fetchDecisionSummary(): Promise<DecisionSummaryResponse> {
  const { data } = await apiClient.get<DecisionSummaryResponse>('/decisions/summary')
  return data
}

export async function fetchDecisionDetail(decisionId: string): Promise<DecisionCard> {
  const { data } = await apiClient.get<DecisionCard>(`/decisions/${encodeURIComponent(decisionId)}`)
  return data
}
