import { useQuery } from '@tanstack/react-query'

import * as projectApi from '../api/projects'
import type { ProjectMember } from '../types'

/** Members of a project, plus a lookup from user id to member (for names/avatars). */
export function useProjectMembers(projectId: string | undefined) {
  const query = useQuery({
    queryKey: ['project-members', projectId],
    queryFn: () => projectApi.listProjectMembers(projectId!),
    enabled: !!projectId,
  })
  const members = query.data ?? []
  const byUserId = new Map<string, ProjectMember>(members.map((m) => [m.user_id, m]))
  return { members, byUserId, isLoading: query.isLoading }
}
