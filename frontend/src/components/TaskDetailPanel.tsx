import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'

import * as activityApi from '../api/activity'
import * as attachmentsApi from '../api/attachments'
import * as commentsApi from '../api/comments'
import * as labelsApi from '../api/labels'
import * as taskApi from '../api/tasks'
import { useAuth } from '../auth/AuthContext'
import { errorMessage, prettySummary, timeAgo } from '../lib/format'
import type { ProjectMember, Task, TaskPriority, TaskStatus } from '../types'
import { Avatar } from './Avatar'

const STATUS_OPTIONS: TaskStatus[] = ['todo', 'in_progress', 'in_review', 'done']
const PRIORITY_OPTIONS: TaskPriority[] = ['low', 'medium', 'high', 'urgent']

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function TaskDetailPanel({
  taskId,
  projectId,
  members,
  onClose,
}: {
  taskId: string
  projectId: string
  members: ProjectMember[]
  onClose: () => void
}) {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const [commentBody, setCommentBody] = useState('')
  const [newLabelName, setNewLabelName] = useState('')
  const [newLabelColor, setNewLabelColor] = useState('#6366f1')
  const [newSubtaskTitle, setNewSubtaskTitle] = useState('')
  const nameOf = (userId: string) =>
    members.find((m) => m.user_id === userId)?.user.full_name ?? 'Someone'
  const fileInputRef = useRef<HTMLInputElement>(null)

  const taskQuery = useQuery({
    queryKey: ['task', taskId],
    queryFn: () => taskApi.getTask(taskId),
  })
  const labelsQuery = useQuery({
    queryKey: ['labels', projectId],
    queryFn: () => labelsApi.listLabels(projectId),
  })
  const commentsQuery = useQuery({
    queryKey: ['comments', taskId],
    queryFn: () => commentsApi.listComments(taskId),
  })
  const attachmentsQuery = useQuery({
    queryKey: ['attachments', taskId],
    queryFn: () => attachmentsApi.listAttachments(taskId),
  })
  const subtasksQuery = useQuery({
    queryKey: ['subtasks', taskId],
    queryFn: () => taskApi.listSubtasks(taskId),
  })
  const activityQuery = useQuery({
    queryKey: ['activity', 'task', taskId],
    queryFn: () => activityApi.listTaskActivity(taskId),
  })

  function invalidateTask() {
    void queryClient.invalidateQueries({ queryKey: ['task', taskId] })
    void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] })
  }

  const updateMutation = useMutation({
    mutationFn: (input: taskApi.TaskUpdateInput) => taskApi.updateTask(taskId, input),
    onSuccess: invalidateTask,
  })

  const deleteMutation = useMutation({
    mutationFn: () => taskApi.deleteTask(taskId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] })
      onClose()
    },
  })

  const createLabelMutation = useMutation({
    mutationFn: () =>
      labelsApi.createLabel(projectId, { name: newLabelName.trim(), color: newLabelColor }),
    onSuccess: () => {
      setNewLabelName('')
      void queryClient.invalidateQueries({ queryKey: ['labels', projectId] })
    },
  })

  const createSubtaskMutation = useMutation({
    mutationFn: (title: string) =>
      taskApi.createTask(projectId, { title, parent_task_id: taskId }),
    onSuccess: () => {
      setNewSubtaskTitle('')
      void queryClient.invalidateQueries({ queryKey: ['subtasks', taskId] })
      void queryClient.invalidateQueries({ queryKey: ['activity', 'task', taskId] })
    },
  })

  const toggleSubtaskMutation = useMutation({
    mutationFn: ({ id, done }: { id: string; done: boolean }) =>
      taskApi.updateTask(id, { status: done ? 'done' : 'todo' }),
    // Flip the checkbox immediately and roll back if the request fails, the
    // same optimistic pattern the board uses for drag-and-drop.
    onMutate: async ({ id, done }) => {
      await queryClient.cancelQueries({ queryKey: ['subtasks', taskId] })
      const previous = queryClient.getQueryData<Task[]>(['subtasks', taskId])
      queryClient.setQueryData<Task[]>(['subtasks', taskId], (old) =>
        old?.map((t) => (t.id === id ? { ...t, status: done ? 'done' : 'todo' } : t)),
      )
      return { previous }
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(['subtasks', taskId], context.previous)
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['subtasks', taskId] })
    },
  })

  const addCommentMutation = useMutation({
    mutationFn: (body: string) => commentsApi.createComment(taskId, body),
    onSuccess: () => {
      setCommentBody('')
      void queryClient.invalidateQueries({ queryKey: ['comments', taskId] })
      void queryClient.invalidateQueries({ queryKey: ['activity', 'task', taskId] })
    },
  })

  const uploadMutation = useMutation({
    mutationFn: (file: File) => attachmentsApi.uploadAttachment(taskId, file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['attachments', taskId] })
      void queryClient.invalidateQueries({ queryKey: ['activity', 'task', taskId] })
    },
  })

  const deleteAttachmentMutation = useMutation({
    mutationFn: (attachmentId: string) => attachmentsApi.deleteAttachment(taskId, attachmentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['attachments', taskId] })
      void queryClient.invalidateQueries({ queryKey: ['activity', 'task', taskId] })
    },
  })

  async function handleDownload(attachmentId: string) {
    const url = await attachmentsApi.getDownloadUrl(taskId, attachmentId)
    window.open(url, '_blank', 'noopener,noreferrer')
  }

  function toggleLabel(labelId: string) {
    const task = taskQuery.data
    if (!task) return
    const current = task.labels.map((l) => l.id)
    const next = current.includes(labelId)
      ? current.filter((id) => id !== labelId)
      : [...current, labelId]
    updateMutation.mutate({ label_ids: next })
  }

  const task = taskQuery.data

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/30" onClick={onClose}>
      <div
        className="h-full w-full max-w-lg overflow-y-auto bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <button type="button" onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700">
            ✕ Close
          </button>
          <button
            type="button"
            onClick={() => confirm('Delete this task?') && deleteMutation.mutate()}
            className="text-sm text-red-500 hover:text-red-700"
          >
            Delete task
          </button>
        </div>

        {!task ? (
          <p className="text-sm text-gray-400">Loading…</p>
        ) : (
          <>
            <input
              defaultValue={task.title}
              onBlur={(e) => {
                if (e.target.value.trim() && e.target.value !== task.title) {
                  updateMutation.mutate({ title: e.target.value.trim() })
                }
              }}
              className="mb-4 w-full border-0 text-lg font-semibold text-gray-900 focus:ring-0 focus:outline-none"
            />

            <div className="mb-4 grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">Status</label>
                <select
                  value={task.status}
                  onChange={(e) =>
                    updateMutation.mutate({ status: e.target.value as TaskStatus })
                  }
                  className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                >
                  {STATUS_OPTIONS.map((status) => (
                    <option key={status} value={status}>
                      {status.replace('_', ' ')}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">Priority</label>
                <select
                  value={task.priority}
                  onChange={(e) =>
                    updateMutation.mutate({ priority: e.target.value as TaskPriority })
                  }
                  className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                >
                  {PRIORITY_OPTIONS.map((priority) => (
                    <option key={priority} value={priority}>
                      {priority}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="mb-4 grid grid-cols-2 gap-3">
              <div>
                <label
                  htmlFor="task-assignee"
                  className="mb-1 block text-xs font-medium text-gray-500"
                >
                  Assignee
                </label>
                <select
                  id="task-assignee"
                  value={task.assignee_id ?? ''}
                  onChange={(e) => updateMutation.mutate({ assignee_id: e.target.value || null })}
                  className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                >
                  <option value="">Unassigned</option>
                  {members.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.user.full_name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-gray-500">Due date</label>
                <input
                  type="date"
                  defaultValue={task.due_date ?? ''}
                  onChange={(e) => updateMutation.mutate({ due_date: e.target.value || null })}
                  className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
                />
              </div>
            </div>
            {updateMutation.isError && (
              <p className="mb-3 text-sm text-red-600">{errorMessage(updateMutation.error)}</p>
            )}

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium text-gray-500">Description</label>
              <textarea
                defaultValue={task.description ?? ''}
                onBlur={(e) => updateMutation.mutate({ description: e.target.value })}
                rows={3}
                className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm"
              />
            </div>

            <div className="mb-4">
              <label className="mb-1 block text-xs font-medium text-gray-500">Labels</label>
              <div className="flex flex-wrap gap-1.5">
                {labelsQuery.data?.length === 0 && (
                  <p className="text-xs text-gray-400">No labels yet. Create the first one below.</p>
                )}
                {labelsQuery.data?.map((label) => {
                  const active = task.labels.some((l) => l.id === label.id)
                  return (
                    <button
                      key={label.id}
                      type="button"
                      onClick={() => toggleLabel(label.id)}
                      className="rounded-full px-2 py-0.5 text-xs font-medium text-white"
                      style={{
                        backgroundColor: label.color,
                        opacity: active ? 1 : 0.35,
                      }}
                    >
                      {label.name}
                    </button>
                  )
                })}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (newLabelName.trim()) createLabelMutation.mutate()
                }}
                className="mt-2 flex items-center gap-2"
              >
                <input
                  type="color"
                  value={newLabelColor}
                  onChange={(e) => setNewLabelColor(e.target.value)}
                  aria-label="Label colour"
                  className="h-7 w-7 cursor-pointer rounded border border-gray-300 p-0.5"
                />
                <input
                  value={newLabelName}
                  onChange={(e) => setNewLabelName(e.target.value)}
                  placeholder="New label name"
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-2 py-1 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={createLabelMutation.isPending || !newLabelName.trim()}
                  className="text-sm text-brand-600 hover:underline disabled:opacity-50"
                >
                  Create
                </button>
              </form>
              {createLabelMutation.isError && (
                <p className="mt-1 text-sm text-red-600">
                  {errorMessage(createLabelMutation.error)}
                </p>
              )}
            </div>

            <section className="mb-6">
              <h3 className="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">
                Subtasks
                {subtasksQuery.data && subtasksQuery.data.length > 0 && (
                  <span className="ml-1 font-normal normal-case">
                    ({subtasksQuery.data.filter((t) => t.status === 'done').length}/
                    {subtasksQuery.data.length} done)
                  </span>
                )}
              </h3>
              <div className="space-y-1">
                {subtasksQuery.data?.map((subtask) => (
                  <label key={subtask.id} className="flex items-center gap-2 text-sm text-gray-800">
                    <input
                      type="checkbox"
                      checked={subtask.status === 'done'}
                      onChange={(e) =>
                        toggleSubtaskMutation.mutate({ id: subtask.id, done: e.target.checked })
                      }
                    />
                    <span className={subtask.status === 'done' ? 'text-gray-400 line-through' : ''}>
                      {subtask.title}
                    </span>
                  </label>
                ))}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (newSubtaskTitle.trim()) createSubtaskMutation.mutate(newSubtaskTitle.trim())
                }}
                className="mt-2 flex gap-2"
              >
                <input
                  value={newSubtaskTitle}
                  onChange={(e) => setNewSubtaskTitle(e.target.value)}
                  placeholder="Add a subtask…"
                  className="min-w-0 flex-1 rounded-lg border border-gray-300 px-2 py-1 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={createSubtaskMutation.isPending || !newSubtaskTitle.trim()}
                  className="text-sm text-brand-600 hover:underline disabled:opacity-50"
                >
                  Add
                </button>
              </form>
            </section>

            <section className="mb-6">
              <h3 className="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">
                Attachments
              </h3>
              <div className="space-y-1.5">
                {attachmentsQuery.data?.map((attachment) => (
                  <div
                    key={attachment.id}
                    className="flex items-center justify-between rounded-lg border border-gray-100 px-3 py-1.5 text-sm"
                  >
                    <button
                      type="button"
                      onClick={() => void handleDownload(attachment.id)}
                      className="truncate text-brand-600 hover:underline"
                    >
                      {attachment.filename}
                    </button>
                    <div className="flex items-center gap-2 text-xs text-gray-400">
                      <span>{formatBytes(attachment.size_bytes)}</span>
                      <button
                        type="button"
                        onClick={() => deleteAttachmentMutation.mutate(attachment.id)}
                        className="text-red-400 hover:text-red-600"
                      >
                        ✕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) uploadMutation.mutate(file)
                  e.target.value = ''
                }}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploadMutation.isPending}
                className="mt-2 text-sm text-brand-600 hover:underline disabled:opacity-50"
              >
                {uploadMutation.isPending ? 'Uploading…' : '+ Add attachment'}
              </button>
            </section>

            <section className="mb-6">
              <h3 className="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">
                Comments
              </h3>
              <div className="space-y-3">
                {commentsQuery.data?.length === 0 && (
                  <p className="text-xs text-gray-400">No comments yet. Start the conversation.</p>
                )}
                {commentsQuery.data?.map((comment) => (
                  <div key={comment.id} className="flex gap-2">
                    <Avatar name={nameOf(comment.author_id)} size="sm" />
                    <div className="min-w-0 flex-1 rounded-lg bg-gray-50 p-3 text-sm">
                      <p className="mb-0.5 text-xs">
                        <span className="font-medium text-gray-700">
                          {nameOf(comment.author_id)}
                        </span>{' '}
                        <span className="text-gray-400">{timeAgo(comment.created_at)}</span>
                      </p>
                      <p className="whitespace-pre-wrap text-gray-800">{comment.body}</p>
                    </div>
                  </div>
                ))}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  if (commentBody.trim()) addCommentMutation.mutate(commentBody.trim())
                }}
                className="mt-3 flex gap-2"
              >
                <input
                  value={commentBody}
                  onChange={(e) => setCommentBody(e.target.value)}
                  placeholder={`Comment as ${user?.full_name ?? ''}… (@email to mention)`}
                  className="flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={addCommentMutation.isPending || !commentBody.trim()}
                  className="rounded-lg bg-brand-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  Send
                </button>
              </form>
            </section>

            <section>
              <h3 className="mb-2 text-xs font-semibold tracking-wide text-gray-500 uppercase">
                Activity
              </h3>
              <div className="space-y-1.5">
                {activityQuery.data?.items.map((entry) => (
                  <p key={entry.id} className="text-xs text-gray-500">
                    <span className="font-medium">{nameOf(entry.actor_id)}</span> {prettySummary(entry.summary)} ·{' '}
                    {timeAgo(entry.created_at)}
                  </p>
                ))}
              </div>
            </section>
          </>
        )}
      </div>
    </div>
  )
}
