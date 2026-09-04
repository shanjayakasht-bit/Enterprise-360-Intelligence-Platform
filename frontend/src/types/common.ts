/** Shared types matching backend/models/common.py */

export interface PageInfo {
  page: number
  page_size: number
  total_items: number
  total_pages: number
}

export interface PaginatedResponse<T> {
  items: T[]
  page_info: PageInfo
}

export interface ApiErrorBody {
  error: string
  message: string
}

export interface HealthResponse {
  status: string
  service: string
  snowflake: string
  version: string
}

export type RiskLevel = 'Low' | 'Medium' | 'High'
