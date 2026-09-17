import type { Notification, Task } from '../types'

export type ProjectWSEventType =
  | 'task_created'
  | 'task_updated'
  | 'task_deleted'
  | 'comment_created'
  | 'attachment_added'
  | 'attachment_removed'
  | 'presence_joined'
  | 'presence_left'
  | 'presence_snapshot'

export interface ProjectWSEvent {
  type: ProjectWSEventType
  project_id: string
  actor_id: string | null
  data: Record<string, unknown>
}

export interface NotificationWSEvent {
  type: 'notification'
  project_id: null
  actor_id: null
  data: Notification
}

export function isProjectWSEvent(value: unknown): value is ProjectWSEvent {
  return (
    typeof value === 'object' &&
    value !== null &&
    'type' in value &&
    (value as { type: unknown }).type !== 'notification'
  )
}

// Partial task data as sent in task_created/task_updated events — mirrors
// task_service._task_broadcast_payload on the backend, which intentionally
// sends a slimmer shape than the full TaskRead schema.
export type TaskEventData = Pick<
  Task,
  'id' | 'title' | 'status' | 'priority' | 'assignee_id' | 'position'
>
