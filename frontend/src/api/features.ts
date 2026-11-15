import { apiClient } from './client'
import type { TaskPriority } from '../types'

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

export interface TaskDraft {
  title: string
  description: string | null
  priority: TaskPriority
  assignee_id: string | null
  due_date: string | null
}

/** Proposed tasks from pasted notes. Saves nothing; the user confirms before creating. */
export async function draftTasks(projectId: string, text: string): Promise<TaskDraft[]> {
  const { data } = await apiClient.post<{ drafts: TaskDraft[] }>(
    `/api/projects/${projectId}/task-drafts`,
    { text },
  )
  return data.drafts
}
