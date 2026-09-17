import { apiClient } from './client'
import type { Comment } from '../types'

export async function listComments(taskId: string): Promise<Comment[]> {
  const { data } = await apiClient.get<Comment[]>(`/api/tasks/${taskId}/comments`)
  return data
}

export async function createComment(taskId: string, body: string): Promise<Comment> {
  const { data } = await apiClient.post<Comment>(`/api/tasks/${taskId}/comments`, { body })
  return data
}
