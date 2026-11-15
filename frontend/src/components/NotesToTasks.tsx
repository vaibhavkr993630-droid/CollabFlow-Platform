import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'

import { draftTasks, type TaskDraft } from '../api/features'
import * as taskApi from '../api/tasks'
import { errorMessage } from '../lib/format'
import type { ProjectMember, TaskPriority } from '../types'

const PRIORITIES: TaskPriority[] = ['low', 'medium', 'high', 'urgent']

type Row = TaskDraft & { selected: boolean }

const inputClass =
  'w-full rounded-md border border-gray-300 px-2 py-1 text-sm focus:border-brand-500 focus:outline-none'

/**
 * Paste notes → review proposed tasks → create the chosen ones. Drafting saves nothing;
 * creation goes through the normal task endpoint, one task at a time.
 */
export function NotesToTasks({
  projectId,
  members,
  onDone,
}: {
  projectId: string
  members: ProjectMember[]
  onDone: () => void
}) {
  const queryClient = useQueryClient()
  const [text, setText] = useState('')
  const [rows, setRows] = useState<Row[] | null>(null)
  const [createError, setCreateError] = useState<string | null>(null)

  const draftMutation = useMutation({
    mutationFn: () => draftTasks(projectId, text.trim()),
    onSuccess: (drafts) => setRows(drafts.map((d) => ({ ...d, selected: true }))),
  })

  const createMutation = useMutation({
    mutationFn: async (chosen: Row[]) => {
      // One at a time, so a failure leaves a clear picture of what was created.
      for (const row of chosen) {
        await taskApi.createTask(projectId, {
          title: row.title.trim(),
          description: row.description ?? undefined,
          priority: row.priority,
          assignee_id: row.assignee_id,
          due_date: row.due_date,
        })
        setRows((current) => current?.filter((r) => r !== row) ?? null)
      }
    },
    onSuccess: () => onDone(),
    onError: (error) =>
      setCreateError(`${errorMessage(error)} Tasks still listed here were not created.`),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ['tasks', projectId] })
      void queryClient.invalidateQueries({ queryKey: ['activity', 'project', projectId] })
    },
  })

  function update(index: number, patch: Partial<Row>) {
    setRows((current) => current?.map((r, i) => (i === index ? { ...r, ...patch } : r)) ?? null)
  }

  if (rows === null) {
    return (
      <div>
        <p className="mb-2 text-sm text-gray-600">
          Paste meeting notes. You'll get a list of proposed tasks to review. Nothing is created
          until you confirm.
        </p>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={8}
          maxLength={8000}
          placeholder="e.g. Arjun will add alerting for stuck orders by Friday…"
          className={inputClass}
        />
        {draftMutation.isError && (
          <p className="mt-2 text-sm text-red-600">{errorMessage(draftMutation.error)}</p>
        )}
        <button
          type="button"
          onClick={() => draftMutation.mutate()}
          disabled={!text.trim() || draftMutation.isPending}
          className="mt-3 w-full rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {draftMutation.isPending ? 'Reading notes…' : 'Find tasks'}
        </button>
      </div>
    )
  }

  const chosen = rows.filter((r) => r.selected && r.title.trim())

  return (
    <div>
      {rows.length === 0 ? (
        <p className="text-sm text-gray-600">No action items found in these notes.</p>
      ) : (
        <ul className="space-y-3">
          {rows.map((row, index) => (
            <li
              key={index}
              className={`rounded-lg border p-2.5 ${row.selected ? 'border-brand-100 bg-brand-50' : 'border-gray-200 opacity-60'}`}
            >
              <div className="mb-1.5 flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={row.selected}
                  onChange={(e) => update(index, { selected: e.target.checked })}
                  aria-label={`Include "${row.title}"`}
                />
                <input
                  value={row.title}
                  onChange={(e) => update(index, { title: e.target.value })}
                  aria-label="Task title"
                  className={inputClass}
                />
              </div>
              {row.description && (
                <p className="mb-1.5 pl-6 text-xs text-gray-500">{row.description}</p>
              )}
              <div className="grid grid-cols-3 gap-1.5 pl-6">
                <select
                  value={row.priority}
                  onChange={(e) => update(index, { priority: e.target.value as TaskPriority })}
                  aria-label="Priority"
                  className={inputClass}
                >
                  {PRIORITIES.map((p) => (
                    <option key={p} value={p}>
                      {p}
                    </option>
                  ))}
                </select>
                <select
                  value={row.assignee_id ?? ''}
                  onChange={(e) => update(index, { assignee_id: e.target.value || null })}
                  aria-label="Assignee"
                  className={inputClass}
                >
                  <option value="">Unassigned</option>
                  {members.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {m.user.full_name}
                    </option>
                  ))}
                </select>
                <input
                  type="date"
                  value={row.due_date ?? ''}
                  onChange={(e) => update(index, { due_date: e.target.value || null })}
                  aria-label="Due date"
                  className={inputClass}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
      {createError && <p className="mt-2 text-sm text-red-600">{createError}</p>}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => {
            setRows(null)
            setCreateError(null)
          }}
          disabled={createMutation.isPending}
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          Back to notes
        </button>
        <button
          type="button"
          onClick={() => {
            setCreateError(null)
            createMutation.mutate(chosen)
          }}
          disabled={chosen.length === 0 || createMutation.isPending}
          className="flex-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {createMutation.isPending
            ? 'Creating…'
            : `Create ${chosen.length} task${chosen.length === 1 ? '' : 's'}`}
        </button>
      </div>
    </div>
  )
}
