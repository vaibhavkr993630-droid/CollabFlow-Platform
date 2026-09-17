export type Role = 'owner' | 'admin' | 'member'

export interface User {
  id: string
  email: string
  full_name: string
  is_active: boolean
}

export interface Organization {
  id: string
  name: string
  slug: string
  owner_id: string
}

export interface Workspace {
  id: string
  name: string
  slug: string
  organization_id: string
}

export interface WorkspaceMember {
  id: string
  user_id: string
  role: Role
}

export interface Project {
  id: string
  name: string
  slug: string
  description: string | null
  workspace_id: string
}

export interface ProjectMember {
  id: string
  user_id: string
  role: Role
}

export type TaskStatus = 'todo' | 'in_progress' | 'in_review' | 'done'
export type TaskPriority = 'low' | 'medium' | 'high' | 'urgent'

export interface Label {
  id: string
  project_id: string
  name: string
  color: string
}

export interface Task {
  id: string
  project_id: string
  title: string
  description: string | null
  status: TaskStatus
  priority: TaskPriority
  assignee_id: string | null
  due_date: string | null
  parent_task_id: string | null
  created_by_id: string
  position: number
  labels: Label[]
  created_at: string
  updated_at: string
}

export interface TaskListResponse {
  items: Task[]
  total: number
  page: number
  page_size: number
}

export interface Comment {
  id: string
  task_id: string
  author_id: string
  body: string
  created_at: string
  updated_at: string
}

export type ActivityAction =
  | 'project_created'
  | 'member_invited'
  | 'task_created'
  | 'task_updated'
  | 'task_deleted'
  | 'comment_added'
  | 'label_created'
  | 'attachment_added'
  | 'attachment_removed'

export interface ActivityLogEntry {
  id: string
  project_id: string
  task_id: string | null
  actor_id: string
  action: ActivityAction
  summary: string
  activity_metadata: Record<string, unknown> | null
  created_at: string
}

export interface ActivityListResponse {
  items: ActivityLogEntry[]
  total: number
  page: number
  page_size: number
}

export type NotificationType =
  | 'mention'
  | 'task_assigned'
  | 'workspace_invite'
  | 'project_invite'
  | 'task_due_soon'

export interface Notification {
  id: string
  type: NotificationType
  title: string
  body: string
  project_id: string | null
  task_id: string | null
  read_at: string | null
  created_at: string
}

export interface NotificationListResponse {
  items: Notification[]
  total: number
  page: number
  page_size: number
}

export interface Attachment {
  id: string
  task_id: string
  uploaded_by_id: string
  filename: string
  content_type: string
  size_bytes: number
  created_at: string
}

export interface PresenceResponse {
  online_user_ids: string[]
}
