import { useCallback } from 'react'

import { tokenStore } from '../api/tokenStore'
import { useWebSocket, type WSStatus } from './useWebSocket'
import type { ProjectWSEvent } from './events'

function wsBaseUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}`
}

export function useProjectSocket(
  projectId: string | null,
  onEvent: (event: ProjectWSEvent) => void,
): WSStatus {
  const getUrl = useCallback(() => {
    if (!projectId) return null
    const token = tokenStore.getAccess()
    if (!token) return null
    return `${wsBaseUrl()}/ws/projects/${projectId}?token=${encodeURIComponent(token)}`
  }, [projectId])

  return useWebSocket(getUrl, (data) => onEvent(data as ProjectWSEvent), projectId !== null)
}
