import { useMutation } from '@tanstack/react-query'

import { findSimilarTasks } from '../api/features'
import { useFeatures } from '../hooks/useFeatures'
import { errorMessage } from '../lib/format'

const STATUS_LABEL = { todo: 'To do', in_progress: 'In progress', in_review: 'In review', done: 'Done' }

/**
 * "Search by meaning" for the text already typed in the board's search box. The keyword filter
 * on the board keeps working as before; this adds a ranked list of tasks close in meaning.
 */
export function SmartSearch({
  projectId,
  query,
  onOpenTask,
}: {
  projectId: string
  query: string
  onOpenTask: (taskId: string) => void
}) {
  const { smartSearch } = useFeatures()
  const text = query.trim()
  const mutation = useMutation({ mutationFn: (q: string) => findSimilarTasks(projectId, q) })

  if (!smartSearch || text.length < 3) return null

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => mutation.mutate(text)}
        disabled={mutation.isPending}
        className="rounded-md border border-brand-100 bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-700 hover:bg-brand-100 disabled:opacity-60"
      >
        {mutation.isPending ? 'Searching…' : `Search by meaning: "${text}"`}
      </button>

      {mutation.isError && (
        <p className="mt-1 text-xs text-red-600">{errorMessage(mutation.error)}</p>
      )}

      {mutation.data && (
        <div className="mt-2 rounded-lg border border-gray-200 bg-white p-2">
          <div className="mb-1 flex items-center justify-between px-1">
            <span className="text-xs font-semibold text-gray-600">
              Closest in meaning to "{mutation.variables}"
            </span>
            <button
              type="button"
              onClick={() => mutation.reset()}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Close
            </button>
          </div>
          {mutation.data.length === 0 ? (
            <p className="px-1 py-1 text-sm text-gray-500">No tasks are close in meaning.</p>
          ) : (
            <ul>
              {mutation.data.map((hit) => (
                <li key={hit.id}>
                  <button
                    type="button"
                    onClick={() => onOpenTask(hit.id)}
                    className="w-full rounded-md px-2 py-1.5 text-left hover:bg-gray-50"
                  >
                    <span className="flex items-center gap-2">
                      <span className="text-sm font-medium text-gray-900">{hit.title}</span>
                      <span className="text-xs text-gray-400">{STATUS_LABEL[hit.status]}</span>
                    </span>
                    {hit.matched_text !== hit.title && (
                      <span className="block truncate text-xs text-gray-500">
                        {hit.matched_in === 'comment' ? 'Comment · ' : ''}
                        {hit.matched_text}
                      </span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
