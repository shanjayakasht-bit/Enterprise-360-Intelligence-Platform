import { apiClient } from './client'
import type { ServiceMeta } from '@/types/metadata'

export async function fetchRegions(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>('/metadata/regions')
  return data
}

export async function fetchServices(): Promise<ServiceMeta[]> {
  const { data } = await apiClient.get<ServiceMeta[]>('/metadata/services')
  return data
}

export async function fetchSegments(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>('/metadata/segments')
  return data
}

export async function fetchDepartments(): Promise<string[]> {
  const { data } = await apiClient.get<string[]>('/metadata/departments')
  return data
}
