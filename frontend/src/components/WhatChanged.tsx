import { useMutation } from '@tanstack/react-query'
import { useState } from 'react'

import { getProjectDigest } from '../api/features'
import { errorMessage } from '../lib/format'

const PERIODS = [
  { days: 1, label: 'Last day' },
  { days: 7, label: 'Last 7 days' },
  { days: 14, label: 'Last 14 days' },
  { days: 30, label: 'Last 30 days' },
]

/**
 * "What changed": a short recap of recent activity, comments and what needs attention.
 * Built on the server from the activity log, comments and database counts; deleted tasks
 * are never included.
 */
export function WhatChanged({ projectId }: { projectId: string }) {
  const [days, setDays] = useState(7)
  const mutation = useMutation({ mutationFn: (d: number) => getProjectDigest(projectId, d) })

  return (
    <div>
      <div className="flex gap-2">
        <select
          value={days}
          onChange={(e) => setDays(Number(e.target.value))}
          aria-label="Period"
          className="rounded-lg border border-gray-300 px-3 py-2 text-sm focus:border-brand-500 focus:outline-none"
        >
          {PERIODS.map((p) => (
            <option key={p.days} value={p.days}>
              {p.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => mutation.mutate(days)}
          disabled={mutation.isPending}
          className="flex-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          {mutation.isPending ? 'Reading recent activity…' : 'Show what changed'}
        </button>
      </div>

      {mutation.isError && (
        <p className="mt-3 text-sm text-red-600">{errorMessage(mutation.error)}</p>
      )}

      {mutation.data && (
        <div className="mt-3">
          <p className="mb-1 text-xs text-gray-500">
            {PERIODS.find((p) => p.days === mutation.data.days)?.label ?? `Last ${mutation.data.days} days`}
          </p>
          <p className="rounded-lg bg-gray-50 p-3 text-sm whitespace-pre-line text-gray-800">
            {mutation.data.digest}
          </p>
        </div>
      )}
    </div>
  )
}
