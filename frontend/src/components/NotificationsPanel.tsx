import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import * as notificationsApi from '../api/notifications'
import { useAuth } from '../auth/AuthContext'
import type { Notification } from '../types'
import { useNotificationSocket } from '../ws/useNotificationSocket'

function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

export function NotificationsPanel() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [isOpen, setIsOpen] = useState(false)

  const unreadQuery = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.getUnreadCount,
    enabled: !!user,
  })

  const listQuery = useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => notificationsApi.listNotifications(),
    enabled: isOpen,
  })

  useNotificationSocket(!!user, () => {
    // A live notification means the unread count and (if open) the list are
    // both stale — invalidate rather than trying to splice the event's
    // payload into cache by hand, since the REST shape and the WS payload
    // shape are allowed to drift independently.
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  })

  async function handleMarkRead(notification: Notification) {
    if (notification.read_at) return
    await notificationsApi.markNotificationRead(notification.id)
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  }

  async function handleMarkAllRead() {
    await notificationsApi.markAllRead()
    void queryClient.invalidateQueries({ queryKey: ['notifications'] })
  }

  const unreadCount = unreadQuery.data ?? 0

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="relative rounded-full p-2 text-gray-500 hover:bg-gray-100 hover:text-gray-700"
        aria-label="Notifications"
      >
        <BellIcon />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium text-white">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute right-0 z-20 mt-2 w-80 rounded-xl border border-gray-200 bg-white shadow-lg">
            <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
              <span className="text-sm font-semibold text-gray-900">Notifications</span>
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={() => void handleMarkAllRead()}
                  className="text-xs font-medium text-brand-600 hover:underline"
                >
                  Mark all read
                </button>
              )}
            </div>
            <div className="max-h-96 overflow-y-auto">
              {listQuery.isLoading && (
                <p className="px-4 py-6 text-center text-sm text-gray-400">Loading…</p>
              )}
              {listQuery.data?.items.length === 0 && (
                <p className="px-4 py-6 text-center text-sm text-gray-400">
                  No notifications yet.
                </p>
              )}
              {listQuery.data?.items.map((notification) => (
                <button
                  key={notification.id}
                  type="button"
                  onClick={() => void handleMarkRead(notification)}
                  className={`block w-full border-b border-gray-50 px-4 py-3 text-left text-sm last:border-0 hover:bg-gray-50 ${
                    notification.read_at ? '' : 'bg-brand-50/50'
                  }`}
                >
                  <p className="font-medium text-gray-900">{notification.title}</p>
                  <p className="mt-0.5 text-gray-500">{notification.body}</p>
                  <p className="mt-1 text-xs text-gray-400">
                    {timeAgo(notification.created_at)}
                  </p>
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}

function BellIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      className="h-5 w-5"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M14.857 17.082a23.848 23.848 0 0 0 5.454-1.31A8.967 8.967 0 0 1 18 9.75V9A6 6 0 0 0 6 9v.75a8.967 8.967 0 0 1-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 0 1-5.714 0m5.714 0a3 3 0 1 1-5.714 0"
      />
    </svg>
  )
}
