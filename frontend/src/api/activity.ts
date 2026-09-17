import { apiClient } from './client'
import type { ActivityListResponse } from '../types'

export async function listProjectActivity(
  projectId: string,
  page = 1,
  pageSize = 20,
): Promise<ActivityListResponse> {
  const { data } = await apiClient.get<ActivityListResponse>(
    `/api/projects/${projectId}/activity`,
    { params: { page, page_size: pageSize } },
  )
  return data
}

export async function listTaskActivity(
  taskId: string,
  page = 1,
  pageSize = 20,
): Promise<ActivityListResponse> {
  const { data } = await apiClient.get<ActivityListResponse>(`/api/tasks/${taskId}/activity`, {
    params: { page, page_size: pageSize },
  })
  return data
}
