import { apiClient } from './client'
import type { PresenceResponse, Project, ProjectMember } from '../types'

export async function listProjects(workspaceId: string): Promise<Project[]> {
  const { data } = await apiClient.get<Project[]>(`/api/workspaces/${workspaceId}/projects`)
  return data
}

export async function createProject(
  workspaceId: string,
  input: { name: string; description?: string },
): Promise<Project> {
  const { data } = await apiClient.post<Project>(
    `/api/workspaces/${workspaceId}/projects`,
    input,
  )
  return data
}

export async function listProjectMembers(projectId: string): Promise<ProjectMember[]> {
  const { data } = await apiClient.get<ProjectMember[]>(`/api/projects/${projectId}/members`)
  return data
}

export async function inviteProjectMember(
  projectId: string,
  email: string,
  role: string,
): Promise<ProjectMember> {
  const { data } = await apiClient.post<ProjectMember>(`/api/projects/${projectId}/members`, {
    email,
    role,
  })
  return data
}

export async function getProjectPresence(projectId: string): Promise<PresenceResponse> {
  const { data } = await apiClient.get<PresenceResponse>(`/api/projects/${projectId}/presence`)
  return data
}
