import { apiClient } from './client'
import type { Label } from '../types'

export async function listLabels(projectId: string): Promise<Label[]> {
  const { data } = await apiClient.get<Label[]>(`/api/projects/${projectId}/labels`)
  return data
}

export async function createLabel(
  projectId: string,
  input: { name: string; color?: string },
): Promise<Label> {
  const { data } = await apiClient.post<Label>(`/api/projects/${projectId}/labels`, input)
  return data
}
