import { apiClient } from './client'
import type { Task, TaskListResponse, TaskPriority, TaskStatus } from '../types'

export interface TaskFilters {
  status?: TaskStatus
  priority?: TaskPriority
  assignee_id?: string
  label_id?: string
  search?: string
  sort_by?: string
  sort_order?: 'asc' | 'desc'
  page?: number
  page_size?: number
}

export async function listTasks(
  projectId: string,
  filters: TaskFilters = {},
): Promise<TaskListResponse> {
  const { data } = await apiClient.get<TaskListResponse>(`/api/projects/${projectId}/tasks`, {
    params: filters,
  })
  return data
}

export interface TaskCreateInput {
  title: string
  description?: string
  status?: TaskStatus
  priority?: TaskPriority
  assignee_id?: string | null
  due_date?: string | null
  parent_task_id?: string | null
}

export async function createTask(projectId: string, input: TaskCreateInput): Promise<Task> {
  const { data } = await apiClient.post<Task>(`/api/projects/${projectId}/tasks`, input)
  return data
}

export async function getTask(taskId: string): Promise<Task> {
  const { data } = await apiClient.get<Task>(`/api/tasks/${taskId}`)
  return data
}

export interface TaskUpdateInput {
  title?: string
  description?: string
  status?: TaskStatus
  priority?: TaskPriority
  assignee_id?: string | null
  due_date?: string | null
  label_ids?: string[]
}

export async function updateTask(taskId: string, input: TaskUpdateInput): Promise<Task> {
  const { data } = await apiClient.patch<Task>(`/api/tasks/${taskId}`, input)
  return data
}

export async function deleteTask(taskId: string): Promise<void> {
  await apiClient.delete(`/api/tasks/${taskId}`)
}

export async function listSubtasks(taskId: string): Promise<Task[]> {
  const { data } = await apiClient.get<Task[]>(`/api/tasks/${taskId}/subtasks`)
  return data
}
