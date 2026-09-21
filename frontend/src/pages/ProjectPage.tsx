import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { isAxiosError } from 'axios'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import * as labelsApi from '../api/labels'
import * as projectApi from '../api/projects'
import * as taskApi from '../api/tasks'
import { ActivityPanel } from '../components/ActivityPanel'
import { Avatar } from '../components/Avatar'
import { BoardFilters } from '../components/BoardFilters'
import { KanbanBoard } from '../components/KanbanBoard'
import { Layout } from '../components/Layout'
import { MembersPanel } from '../components/MembersPanel'
import { Modal } from '../components/Modal'
import { TaskDetailPanel } from '../components/TaskDetailPanel'
import { useProjectMembers } from '../hooks/useProjectMembers'
import { EMPTY_FILTERS, type BoardFilterState } from '../lib/boardFilters'
import { errorMessage } from '../lib/format'
import type { Role, Task, TaskListResponse, TaskStatus } from '../types'
import type { ProjectWSEvent } from '../ws/events'
import { useProjectSocket } from '../ws/useProjectSocket'

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [onlineUserIds, setOnlineUserIds] = useState<string[]>([])
  const [filters, setFilters] = useState<BoardFilterState>(EMPTY_FILTERS)
  const [showMembers, setShowMembers] = useState(false)
  const [showActivity, setShowActivity] = useState(false)

  const { members, byUserId, isLoading: membersLoading } = useProjectMembers(projectId)
  const assigneeNames = new Map(members.map((m) => [m.user_id, m.user.full_name]))

  const projectQuery = useQuery({
    queryKey: ['project', projectId],
    queryFn: () => projectApi.getProject(projectId!),
    enabled: !!projectId,
    retry: false,
  })

  const labelsQuery = useQuery({
    queryKey: ['labels', projectId],
    queryFn: () => labelsApi.listLabels(projectId!),
    enabled: !!projectId && projectQuery.isSuccess,
  })

  // The filters are part of the cache key so each combination is cached on its
  // own, but every live-update handler below invalidates by the ['tasks',
  // projectId] prefix, which matches all of them.
  const tasksQueryKey = ['tasks', projectId, filters] as const
  const tasksPrefix = ['tasks', projectId] as const

  const tasksQuery = useQuery({
    queryKey: tasksQueryKey,
    // 100, not more: the backend caps page_size at 100 (see
    // app/api/routers/tasks.py's Query(..., le=100)) and rejects anything
    // above it with a 422 — a Kanban board wants "everything in one view,"
    // but that view still has to respect the API's actual contract.
    queryFn: () =>
      taskApi.listTasks(projectId!, {
        page_size: 100,
        search: filters.search.trim() || undefined,
        priority: filters.priority || undefined,
        assignee_id: filters.assigneeId || undefined,
        label_id: filters.labelId || undefined,
        // Priority is a database enum ordered low → urgent, so "most urgent
        // first" is descending; "newest first" is likewise descending.
        sort_by: filters.sort,
        sort_order: filters.sort === 'priority' || filters.sort === 'created_at' ? 'desc' : 'asc',
      }),
    enabled: !!projectId && projectQuery.isSuccess,
    placeholderData: (previous) => previous,
  })

  const presenceQuery = useQuery({
    queryKey: ['presence', projectId],
    queryFn: () => projectApi.getProjectPresence(projectId!),
    enabled: !!projectId && projectQuery.isSuccess,
  })

  const statusMutation = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: TaskStatus }) =>
      taskApi.updateTask(taskId, { status }),
    onMutate: async ({ taskId, status }) => {
      await queryClient.cancelQueries({ queryKey: tasksPrefix })
      const previous = queryClient.getQueryData<TaskListResponse>(tasksQueryKey)
      queryClient.setQueryData<TaskListResponse>(tasksQueryKey, (old) =>
        old
          ? { ...old, items: old.items.map((t) => (t.id === taskId ? { ...t, status } : t)) }
          : old,
      )
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(tasksQueryKey, context.previous)
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: tasksPrefix })
    },
  })

  const inviteMutation = useMutation({
    mutationFn: ({ email, role }: { email: string; role: Role }) =>
      projectApi.inviteProjectMember(projectId!, email, role),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['project-members', projectId] })
      void queryClient.invalidateQueries({ queryKey: ['activity', 'project', projectId] })
    },
  })

  const createTaskMutation = useMutation({
    mutationFn: (title: string) => taskApi.createTask(projectId!, { title }),
    onSuccess: () => {
      setNewTaskTitle('')
      void queryClient.invalidateQueries({ queryKey: tasksPrefix })
      void queryClient.invalidateQueries({ queryKey: ['activity', 'project', projectId] })
    },
  })

  useProjectSocket(projectQuery.isSuccess ? (projectId ?? null) : null, (event: ProjectWSEvent) => {
    switch (event.type) {
      case 'task_created':
      case 'task_updated':
      case 'task_deleted':
        void queryClient.invalidateQueries({ queryKey: tasksPrefix })
        void queryClient.invalidateQueries({ queryKey: ['subtasks'] })
        void queryClient.invalidateQueries({ queryKey: ['activity', 'project', projectId] })
        break
      case 'comment_created':
      case 'attachment_added':
      case 'attachment_removed': {
        const taskId = (event.data as { task_id?: string }).task_id
        if (taskId) {
          void queryClient.invalidateQueries({ queryKey: ['comments', taskId] })
          void queryClient.invalidateQueries({ queryKey: ['attachments', taskId] })
          void queryClient.invalidateQueries({ queryKey: ['activity', 'task', taskId] })
        }
        void queryClient.invalidateQueries({ queryKey: ['activity', 'project', projectId] })
        break
      }
      case 'presence_snapshot':
        setOnlineUserIds((event.data as { online_user_ids: string[] }).online_user_ids)
        break
      case 'presence_joined': {
        const userId = (event.data as { user_id: string }).user_id
        setOnlineUserIds((ids) => (ids.includes(userId) ? ids : [...ids, userId]))
        break
      }
      case 'presence_left': {
        const userId = (event.data as { user_id: string }).user_id
        setOnlineUserIds((ids) => ids.filter((id) => id !== userId))
        break
      }
    }
  })

  if (!projectId) return null

  if (projectQuery.isError) {
    const status = isAxiosError(projectQuery.error) ? projectQuery.error.response?.status : undefined
    return (
      <Layout>
        <div className="mx-auto mt-16 max-w-md rounded-xl border border-gray-200 bg-white p-8 text-center">
          <h1 className="mb-2 text-lg font-semibold text-gray-900">
            {status === 403 ? "You're not a member of this project" : "Couldn't open this project"}
          </h1>
          <p className="mb-4 text-sm text-gray-500">
            {status === 403
              ? 'Being in the workspace lets you see the project exists. To open its board, an owner or admin of the project needs to add you to it.'
              : errorMessage(projectQuery.error)}
          </p>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Back to dashboard
          </button>
        </div>
      </Layout>
    )
  }

  const tasks = tasksQuery.data?.items ?? []
  const hasFilters = !!(filters.search || filters.priority || filters.assigneeId || filters.labelId)
  // The WS presence state (kept live from the moment we connect) takes over
  // from the initial REST snapshot once it has anything to say — the REST
  // call is just what fills the gap before the socket's own snapshot arrives.
  const online =
    onlineUserIds.length > 0 ? onlineUserIds : (presenceQuery.data?.online_user_ids ?? [])
  const onlineMembers = online.map((id) => byUserId.get(id)).filter((m) => !!m)

  return (
    <Layout>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <button
            type="button"
            onClick={() => navigate('/')}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            ← Dashboard
          </button>
          <h1 className="truncate text-xl font-semibold text-gray-900">
            {projectQuery.data?.name ?? '…'}
          </h1>
          {projectQuery.data?.description && (
            <p className="text-sm text-gray-500">{projectQuery.data.description}</p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 text-xs text-gray-500" title="Online now">
            <span className="h-2 w-2 rounded-full bg-green-500" />
            {online.length} online
            <span className="flex -space-x-1.5">
              {onlineMembers.slice(0, 4).map((m) => (
                <span key={m.user_id} className="rounded-full ring-2 ring-white">
                  <Avatar name={m.user.full_name} size="sm" />
                </span>
              ))}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setShowMembers(true)}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            Members ({members.length})
          </button>
          <button
            type="button"
            onClick={() => setShowActivity(true)}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 hover:bg-gray-50"
          >
            Activity
          </button>
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (newTaskTitle.trim()) createTaskMutation.mutate(newTaskTitle.trim())
        }}
        className="mb-3 flex gap-2"
      >
        <input
          value={newTaskTitle}
          onChange={(e) => setNewTaskTitle(e.target.value)}
          placeholder="Quick-add a task…"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={createTaskMutation.isPending || !newTaskTitle.trim()}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          Add task
        </button>
      </form>
      {createTaskMutation.isError && (
        <p className="mb-3 text-sm text-red-600">{errorMessage(createTaskMutation.error)}</p>
      )}

      <BoardFilters
        value={filters}
        onChange={setFilters}
        members={members}
        labels={labelsQuery.data ?? []}
      />

      {projectQuery.isLoading || tasksQuery.isLoading ? (
        <p className="text-sm text-gray-400">Loading tasks…</p>
      ) : tasksQuery.isError ? (
        <p className="text-sm text-red-500">Couldn't load tasks. Try refreshing the page.</p>
      ) : (
        <>
          {tasks.length === 0 && (
            <p className="mb-3 rounded-lg border border-dashed border-gray-300 bg-white px-4 py-3 text-sm text-gray-500">
              {hasFilters
                ? 'No tasks match these filters.'
                : 'No tasks yet. Quick-add one above, then drag it across the columns as work progresses.'}
            </p>
          )}
          <KanbanBoard
            tasks={tasks}
            assigneeNames={assigneeNames}
            keepServerOrder={filters.sort !== 'position'}
            onStatusChange={(taskId, status) => statusMutation.mutate({ taskId, status })}
            onTaskClick={(task: Task) => setSelectedTaskId(task.id)}
          />
        </>
      )}

      {selectedTaskId && (
        <TaskDetailPanel
          taskId={selectedTaskId}
          projectId={projectId}
          members={members}
          onClose={() => setSelectedTaskId(null)}
        />
      )}

      {showMembers && (
        <Modal title="Project members" onClose={() => setShowMembers(false)}>
          <MembersPanel
            noun="project"
            members={members}
            isLoading={membersLoading}
            onInvite={(email, role) => inviteMutation.mutateAsync({ email, role })}
          />
        </Modal>
      )}

      {showActivity && (
        <ActivityPanel
          projectId={projectId}
          byUserId={byUserId}
          onClose={() => setShowActivity(false)}
        />
      )}
    </Layout>
  )
}
