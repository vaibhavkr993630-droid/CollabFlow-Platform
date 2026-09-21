import { useCallback } from 'react'

import { tokenStore } from '../api/tokenStore'
import { useWebSocket, type WSStatus } from './useWebSocket'
import { wsBaseUrl } from './wsBaseUrl'
import type { NotificationWSEvent } from './events'

export function useNotificationSocket(
  enabled: boolean,
  onEvent: (event: NotificationWSEvent) => void,
): WSStatus {
  const getUrl = useCallback(() => {
    const token = tokenStore.getAccess()
    if (!token) return null
    return `${wsBaseUrl()}/ws/notifications?token=${encodeURIComponent(token)}`
  }, [])

  return useWebSocket(getUrl, (data) => onEvent(data as NotificationWSEvent), enabled)
}
