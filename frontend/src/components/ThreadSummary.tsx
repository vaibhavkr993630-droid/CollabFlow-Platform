import { useMutation } from '@tanstack/react-query'

import { summarizeThread } from '../api/features'
import { useFeatures } from '../hooks/useFeatures'
import { errorMessage } from '../lib/format'

/** Must match MIN_COMMENTS in backend/app/assistant/summaries.py. */
const MIN_COMMENTS = 6

/**
 * "Summarize thread" for long comment threads. Renders nothing when the feature is off or
 * the thread is short. The parent passes `key={commentCount}`, so a new comment resets it.
 */
export function ThreadSummary({ taskId, commentCount }: { taskId: string; commentCount: number }) {
  const { assistant } = useFeatures()
  const mutation = useMutation({ mutationFn: () => summarizeThread(taskId) })

  if (!assistant || commentCount < MIN_COMMENTS) return null

  if (mutation.data) {
    return (
      <div className="mb-3 rounded-lg border border-brand-100 bg-brand-50 p-3 text-sm text-gray-800">
        <div className="mb-1 flex items-center justify-between">
          <span className="text-xs font-semibold text-brand-700">
            Summary of {mutation.data.comment_count} comments
          </span>
          <button
            type="button"
            onClick={() => mutation.reset()}
            className="text-xs text-gray-500 hover:text-gray-700"
          >
            Hide
          </button>
        </div>
        <p className="whitespace-pre-line">{mutation.data.summary}</p>
      </div>
    )
  }

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
        className="rounded-md border border-brand-100 px-2.5 py-1 text-xs font-medium text-brand-700 hover:bg-brand-50 disabled:opacity-60"
      >
        {mutation.isPending ? 'Summarizing…' : `Summarize ${commentCount} comments`}
      </button>
      {mutation.isError && (
        <p className="mt-1 text-xs text-red-600">{errorMessage(mutation.error)}</p>
      )}
    </div>
  )
}
