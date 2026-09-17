import { useDroppable } from '@dnd-kit/core'
import { SortableContext, verticalListSortingStrategy } from '@dnd-kit/sortable'

import type { Task } from '../types'
import { TaskCard } from './TaskCard'

export function KanbanColumn({
  id,
  title,
  tasks,
  onTaskClick,
}: {
  id: string
  title: string
  tasks: Task[]
  onTaskClick: (task: Task) => void
}) {
  const { setNodeRef, isOver } = useDroppable({ id })

  return (
    <div
      ref={setNodeRef}
      className={`flex flex-col rounded-xl border bg-gray-50 p-3 ${
        isOver ? 'border-brand-400 bg-brand-50/40' : 'border-gray-200'
      }`}
    >
      <div className="mb-3 flex items-center justify-between px-1">
        <h3 className="text-sm font-semibold text-gray-600">{title}</h3>
        <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs text-gray-600">
          {tasks.length}
        </span>
      </div>
      <SortableContext items={tasks.map((t) => t.id)} strategy={verticalListSortingStrategy}>
        <div className="min-h-16 flex-1 space-y-2">
          {tasks.map((task) => (
            <TaskCard key={task.id} task={task} onClick={() => onTaskClick(task)} />
          ))}
        </div>
      </SortableContext>
    </div>
  )
}
