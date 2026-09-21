import { useInfiniteQuery } from '@tanstack/react-query'

import * as activityApi from '../api/activity'
import { prettySummary, timeAgo } from '../lib/format'
import type { ProjectMember } from '../types'
import { Avatar } from './Avatar'

/** Slide-over feed of everything that happened in a project, newest first. */
export function ActivityPanel({
  projectId,
  byUserId,
  onClose,
}: {
  projectId: string
  byUserId: Map<string, ProjectMember>
  onClose: () => void
}) {
  const query = useInfiniteQuery({
    queryKey: ['activity', 'project', projectId],
    queryFn: ({ pageParam }) => activityApi.listProjectActivity(projectId, pageParam, 20),
    initialPageParam: 1,
    getNextPageParam: (last) =>
      last.page * last.page_size < last.total ? last.page + 1 : undefined,
  })

  const entries = query.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <div className="fixed inset-0 z-30 flex justify-end bg-black/30" onClick={onClose}>
      <aside
        aria-label="Project activity"
        className="h-full w-full max-w-md overflow-y-auto bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-base font-semibold text-gray-900">Project activity</h2>
          <button type="button" onClick={onClose} className="text-sm text-gray-500 hover:text-gray-700">
            ✕ Close
          </button>
        </div>

        {query.isLoading ? (
          <p className="text-sm text-gray-400">Loading activity…</p>
        ) : query.isError ? (
          <p className="text-sm text-red-500">Couldn't load activity.</p>
        ) : entries.length === 0 ? (
          <p className="text-sm text-gray-400">
            Nothing has happened yet. Create a task or leave a comment and it will show up here.
          </p>
        ) : (
          <ul className="space-y-3">
            {entries.map((entry) => {
              const actor = byUserId.get(entry.actor_id)?.user.full_name ?? 'Someone'
              return (
                <li key={entry.id} className="flex gap-3">
                  <Avatar name={actor} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-800">
                      <span className="font-medium">{actor}</span> {prettySummary(entry.summary)}
                    </p>
                    <p className="text-xs text-gray-400">{timeAgo(entry.created_at)}</p>
                  </div>
                </li>
              )
            })}
          </ul>
        )}

        {query.hasNextPage && (
          <button
            type="button"
            onClick={() => void query.fetchNextPage()}
            disabled={query.isFetchingNextPage}
            className="mt-4 text-sm text-brand-600 hover:underline disabled:opacity-50"
          >
            {query.isFetchingNextPage ? 'Loading…' : 'Load more'}
          </button>
        )}
      </aside>
    </div>
  )
}
