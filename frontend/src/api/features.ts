import { apiClient } from './client'

/** Optional features the server has switched on. Off features are hidden in the UI. */
export interface Features {
  assistant: boolean
}

export async function getFeatures(): Promise<Features> {
  const { data } = await apiClient.get<Features>('/api/features')
  return data
}

export interface ThreadSummary {
  summary: string
  comment_count: number
  cached: boolean
}

export async function summarizeThread(taskId: string): Promise<ThreadSummary> {
  const { data } = await apiClient.post<ThreadSummary>(`/api/tasks/${taskId}/comments/summary`)
  return data
}
