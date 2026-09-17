import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import * as projectApi from '../api/projects'
import * as taskApi from '../api/tasks'
import { KanbanBoard } from '../components/KanbanBoard'
import { Layout } from '../components/Layout'
import { TaskDetailPanel } from '../components/TaskDetailPanel'
import type { Task, TaskListResponse, TaskStatus } from '../types'
import type { ProjectWSEvent } from '../ws/events'
import { useProjectSocket } from '../ws/useProjectSocket'

export default function ProjectPage() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [newTaskTitle, setNewTaskTitle] = useState('')
  const [onlineUserIds, setOnlineUserIds] = useState<string[]>([])

  const tasksQueryKey = ['tasks', projectId] as const

  const tasksQuery = useQuery({
    queryKey: tasksQueryKey,
    // 100, not more: the backend caps page_size at 100 (see
    // app/api/routers/tasks.py's Query(..., le=100)) and rejects anything
    // above it with a 422 — a Kanban board wants "everything in one view,"
    // but that view still has to respect the API's actual contract.
    queryFn: () => taskApi.listTasks(projectId!, { page_size: 100 }),
    enabled: !!projectId,
  })

  const presenceQuery = useQuery({
    queryKey: ['presence', projectId],
    queryFn: () => projectApi.getProjectPresence(projectId!),
    enabled: !!projectId,
  })

  const statusMutation = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: TaskStatus }) =>
      taskApi.updateTask(taskId, { status }),
    onMutate: async ({ taskId, status }) => {
      await queryClient.cancelQueries({ queryKey: tasksQueryKey })
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
      void queryClient.invalidateQueries({ queryKey: tasksQueryKey })
    },
  })

  const createTaskMutation = useMutation({
    mutationFn: (title: string) => taskApi.createTask(projectId!, { title }),
    onSuccess: () => {
      setNewTaskTitle('')
      void queryClient.invalidateQueries({ queryKey: tasksQueryKey })
    },
  })

  useProjectSocket(projectId ?? null, (event: ProjectWSEvent) => {
    switch (event.type) {
      case 'task_created':
      case 'task_updated':
      case 'task_deleted':
        void queryClient.invalidateQueries({ queryKey: tasksQueryKey })
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

  const tasks = tasksQuery.data?.items ?? []
  // The WS presence state (kept live from the moment we connect) takes over
  // from the initial REST snapshot once it has anything to say — the REST
  // call is just what fills the gap before the socket's own snapshot arrives.
  const online =
    onlineUserIds.length > 0 ? onlineUserIds : (presenceQuery.data?.online_user_ids ?? [])

  return (
    <Layout>
      <div className="mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={() => navigate('/')}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          ← Dashboard
        </button>
        <div className="flex items-center gap-2 text-xs text-gray-500">
          <span className="h-2 w-2 rounded-full bg-green-500" />
          {online.length} online
        </div>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (newTaskTitle.trim()) createTaskMutation.mutate(newTaskTitle.trim())
        }}
        className="mb-4 flex gap-2"
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

      {tasksQuery.isLoading ? (
        <p className="text-sm text-gray-400">Loading tasks…</p>
      ) : tasksQuery.isError ? (
        <p className="text-sm text-red-500">
          Couldn't load tasks. Try refreshing the page.
        </p>
      ) : (
        <KanbanBoard
          tasks={tasks}
          onStatusChange={(taskId, status) => statusMutation.mutate({ taskId, status })}
          onTaskClick={(task: Task) => setSelectedTaskId(task.id)}
        />
      )}

      {selectedTaskId && (
        <TaskDetailPanel
          taskId={selectedTaskId}
          projectId={projectId}
          onClose={() => setSelectedTaskId(null)}
        />
      )}
    </Layout>
  )
}
