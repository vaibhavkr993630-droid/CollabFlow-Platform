import { useSortable } from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'

import type { Task } from '../types'

const PRIORITY_STYLES: Record<Task['priority'], string> = {
  low: 'bg-gray-100 text-gray-600',
  medium: 'bg-blue-100 text-blue-700',
  high: 'bg-amber-100 text-amber-700',
  urgent: 'bg-red-100 text-red-700',
}

export function TaskCard({
  task,
  onClick,
  dragging = false,
}: {
  task: Task
  onClick: () => void
  dragging?: boolean
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: task.id,
  })

  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
  }

  return (
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      onClick={onClick}
      className={`cursor-grab space-y-2 rounded-lg border border-gray-200 bg-white p-3 text-left shadow-sm active:cursor-grabbing ${
        dragging ? 'rotate-2 shadow-lg' : 'hover:border-brand-300'
      }`}
    >
      <p className="text-sm font-medium text-gray-900">{task.title}</p>
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${PRIORITY_STYLES[task.priority]}`}
        >
          {task.priority}
        </span>
        {task.labels.map((label) => (
          <span
            key={label.id}
            className="rounded-full px-2 py-0.5 text-[11px] font-medium text-white"
            style={{ backgroundColor: label.color }}
          >
            {label.name}
          </span>
        ))}
      </div>
      {task.due_date && (
        <p className="text-xs text-gray-400">Due {new Date(task.due_date).toLocaleDateString()}</p>
      )}
    </div>
  )
}
