import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'

import { findSimilarTasks } from '../api/features'
import { useFeatures } from '../hooks/useFeatures'

/** Below this length a title is too vague to compare. */
const MIN_TITLE_LENGTH = 12
/** Wait for a pause in typing, so each keystroke does not become a request. */
const TYPING_PAUSE_MS = 700

/**
 * While a new task title is being typed, quietly points out existing tasks that look like the
 * same work. Only very close matches are shown, and nothing blocks creating the task.
 */
export function SimilarTaskHint({
  projectId,
  title,
  onOpenTask,
}: {
  projectId: string
  title: string
  onOpenTask: (taskId: string) => void
}) {
  const { smartSearch } = useFeatures()
  const [settled, setSettled] = useState('')

  useEffect(() => {
    const timer = window.setTimeout(() => setSettled(title.trim()), TYPING_PAUSE_MS)
    return () => window.clearTimeout(timer)
  }, [title])

  const enabled = smartSearch && settled.length >= MIN_TITLE_LENGTH && settled === title.trim()
  const query = useQuery({
    queryKey: ['similar-tasks', projectId, settled],
    queryFn: () => findSimilarTasks(projectId, settled, 'duplicate'),
    enabled,
    staleTime: 60_000,
    retry: false,
  })

  if (!enabled || !query.data?.length) return null

  return (
    <p className="mb-3 text-xs text-amber-700">
      Looks similar to:{' '}
      {query.data.map((hit, index) => (
        <span key={hit.id}>
          {index > 0 && ', '}
          <button
            type="button"
            onClick={() => onOpenTask(hit.id)}
            className="font-medium underline hover:text-amber-900"
          >
            {hit.title}
          </button>
        </span>
      ))}
    </p>
  )
}
