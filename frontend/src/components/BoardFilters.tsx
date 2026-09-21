import type { BoardFilterState } from '../lib/boardFilters'
import { EMPTY_FILTERS } from '../lib/boardFilters'
import type { Label, ProjectMember, TaskPriority } from '../types'

const SELECT_CLASS = 'rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-sm text-gray-700'

export function BoardFilters({
  value,
  onChange,
  members,
  labels,
}: {
  value: BoardFilterState
  onChange: (next: BoardFilterState) => void
  members: ProjectMember[]
  labels: Label[]
}) {
  const active =
    value.search || value.priority || value.assigneeId || value.labelId || value.sort !== 'position'

  function set<K extends keyof BoardFilterState>(key: K, next: BoardFilterState[K]) {
    onChange({ ...value, [key]: next })
  }

  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <input
        type="search"
        value={value.search}
        onChange={(e) => set('search', e.target.value)}
        placeholder="Search tasks…"
        aria-label="Search tasks"
        className="min-w-40 flex-1 rounded-lg border border-gray-300 px-3 py-1.5 text-sm focus:border-brand-500 focus:ring-1 focus:ring-brand-500 focus:outline-none"
      />
      <select
        value={value.priority}
        onChange={(e) => set('priority', e.target.value as TaskPriority | '')}
        aria-label="Filter by priority"
        className={SELECT_CLASS}
      >
        <option value="">Any priority</option>
        <option value="urgent">Urgent</option>
        <option value="high">High</option>
        <option value="medium">Medium</option>
        <option value="low">Low</option>
      </select>
      <select
        value={value.assigneeId}
        onChange={(e) => set('assigneeId', e.target.value)}
        aria-label="Filter by assignee"
        className={SELECT_CLASS}
      >
        <option value="">Anyone</option>
        {members.map((m) => (
          <option key={m.user_id} value={m.user_id}>
            {m.user.full_name}
          </option>
        ))}
      </select>
      <select
        value={value.labelId}
        onChange={(e) => set('labelId', e.target.value)}
        aria-label="Filter by label"
        className={SELECT_CLASS}
      >
        <option value="">Any label</option>
        {labels.map((l) => (
          <option key={l.id} value={l.id}>
            {l.name}
          </option>
        ))}
      </select>
      <select
        value={value.sort}
        onChange={(e) => set('sort', e.target.value as BoardFilterState['sort'])}
        aria-label="Sort tasks"
        className={SELECT_CLASS}
      >
        <option value="position">Board order</option>
        <option value="due_date">Sort: due date</option>
        <option value="priority">Sort: priority</option>
        <option value="created_at">Sort: newest</option>
        <option value="title">Sort: title</option>
      </select>
      {active && (
        <button
          type="button"
          onClick={() => onChange(EMPTY_FILTERS)}
          className="text-sm text-brand-600 hover:underline"
        >
          Clear
        </button>
      )}
    </div>
  )
}
