import { apiClient } from './client'
import type { PaginatedResponse } from '@/types/common'
import type { ProjectDetail, ProjectRiskCard } from '@/types/project'

export interface ProjectRiskParams {
  page?: number
  page_size?: number
  risk_level?: string
  department?: string
  customer_id?: string
}

export async function fetchProjectRisk(params: ProjectRiskParams): Promise<PaginatedResponse<ProjectRiskCard>> {
  const { data } = await apiClient.get<PaginatedResponse<ProjectRiskCard>>('/projects/risk', { params })
  return data
}

export async function fetchProjectDetail(projectId: string): Promise<ProjectDetail> {
  const { data } = await apiClient.get<ProjectDetail>(`/projects/${encodeURIComponent(projectId)}`)
  return data
}
