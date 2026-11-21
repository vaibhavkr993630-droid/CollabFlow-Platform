import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { askProject } from '../api/features'
import { errorMessage } from '../lib/format'

const EXAMPLES = ['Why are card payments failing?', 'What did we decide about refunds?']

/**
 * Ask a question about this project. The answer comes only from the project's own tasks and
 * comments and cites them as [n]; each cited source links to its task.
 */
export function AskProject({
  projectId,
  onOpenTask,
}: {
  projectId: string
  onOpenTask: (taskId: string) => void
}) {
  const [question, setQuestion] = useState('')
  const mutation = useMutation({ mutationFn: (q: string) => askProject(projectId, q) })

  function ask(q: string) {
    if (q.trim().length >= 3) mutation.mutate(q.trim())
  }

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          ask(question)
        }}
        className="flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          maxLength={500}
          placeholder="Ask about this project's tasks and discussions…"
          aria-label="Question"
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={question.trim().length < 3 || mutation.isPending}
          className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {mutation.isPending ? 'Thinking…' : 'Ask'}
        </button>
      </form>

      {!mutation.data && !mutation.isPending && !mutation.isError && (
        <p className="mt-2 text-xs text-gray-500">
          Try:{' '}
          {EXAMPLES.map((example, index) => (
            <span key={example}>
              {index > 0 && ' · '}
              <button
                type="button"
                onClick={() => {
                  setQuestion(example)
                  ask(example)
                }}
                className="text-brand-600 hover:underline"
              >
                {example}
              </button>
            </span>
          ))}
        </p>
      )}

      {mutation.isPending && (
        <p className="mt-3 text-sm text-gray-500">Reading the project's tasks and comments…</p>
      )}
      {mutation.isError && (
        <p className="mt-3 text-sm text-red-600">{errorMessage(mutation.error)}</p>
      )}

      {mutation.data && (
        <div className="mt-3">
          <p className="rounded-lg bg-gray-50 p-3 text-sm whitespace-pre-line text-gray-800">
            {mutation.data.answer}
          </p>
          {mutation.data.sources.length > 0 && (
            <div className="mt-3">
              <h3 className="mb-1 text-xs font-semibold tracking-wide text-gray-500 uppercase">
                Sources
              </h3>
              <ul className="space-y-1">
                {mutation.data.sources.map((source) => (
                  <li key={source.number}>
                    <button
                      type="button"
                      onClick={() => onOpenTask(source.task_id)}
                      className="w-full rounded-md px-2 py-1 text-left hover:bg-gray-50"
                    >
                      <span className="text-sm text-gray-900">
                        <span className="mr-1 font-semibold text-brand-700">[{source.number}]</span>
                        {source.task_title}
                        <span className="ml-1 text-xs text-gray-400">({source.kind})</span>
                      </span>
                      <span className="block truncate pl-6 text-xs text-gray-500">
                        {source.snippet}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
