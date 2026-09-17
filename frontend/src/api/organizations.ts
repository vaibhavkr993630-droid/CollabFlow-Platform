import { apiClient } from './client'
import type { Organization, Workspace, WorkspaceMember } from '../types'

export async function listOrganizations(): Promise<Organization[]> {
  const { data } = await apiClient.get<Organization[]>('/api/organizations')
  return data
}

export async function createOrganization(name: string): Promise<Organization> {
  const { data } = await apiClient.post<Organization>('/api/organizations', { name })
  return data
}

export async function listWorkspaces(organizationId: string): Promise<Workspace[]> {
  const { data } = await apiClient.get<Workspace[]>(
    `/api/organizations/${organizationId}/workspaces`,
  )
  return data
}

export async function createWorkspace(
  organizationId: string,
  name: string,
): Promise<Workspace> {
  const { data } = await apiClient.post<Workspace>(
    `/api/organizations/${organizationId}/workspaces`,
    { name },
  )
  return data
}

export async function listWorkspaceMembers(workspaceId: string): Promise<WorkspaceMember[]> {
  const { data } = await apiClient.get<WorkspaceMember[]>(
    `/api/workspaces/${workspaceId}/members`,
  )
  return data
}

export async function inviteWorkspaceMember(
  workspaceId: string,
  email: string,
  role: string,
): Promise<WorkspaceMember> {
  const { data } = await apiClient.post<WorkspaceMember>(
    `/api/workspaces/${workspaceId}/members`,
    { email, role },
  )
  return data
}
