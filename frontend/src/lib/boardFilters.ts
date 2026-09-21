import type { TaskPriority } from '../types'

export interface BoardFilterState {
  search: string
  priority: TaskPriority | ''
  assigneeId: string
  labelId: string
  sort: 'position' | 'due_date' | 'priority' | 'created_at' | 'title'
}

export const EMPTY_FILTERS: BoardFilterState = {
  search: '',
  priority: '',
  assigneeId: '',
  labelId: '',
  sort: 'position',
}
