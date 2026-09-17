import { apiClient } from './client'
import type { Notification, NotificationListResponse } from '../types'

export async function listNotifications(
  page = 1,
  pageSize = 20,
): Promise<NotificationListResponse> {
  const { data } = await apiClient.get<NotificationListResponse>('/api/notifications', {
    params: { page, page_size: pageSize },
  })
  return data
}

export async function getUnreadCount(): Promise<number> {
  const { data } = await apiClient.get<{ unread_count: number }>(
    '/api/notifications/unread-count',
  )
  return data.unread_count
}

export async function markNotificationRead(notificationId: string): Promise<Notification> {
  const { data } = await apiClient.post<Notification>(
    `/api/notifications/${notificationId}/read`,
  )
  return data
}

export async function markAllRead(): Promise<number> {
  const { data } = await apiClient.post<{ marked_read: number }>('/api/notifications/read-all')
  return data.marked_read
}
