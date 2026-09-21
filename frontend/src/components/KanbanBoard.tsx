import {
  DndContext,
  DragOverlay,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragStartEvent,
} from '@dnd-kit/core'
import { useState } from 'react'

import type { Task, TaskStatus } from '../types'
import { KanbanColumn } from './KanbanColumn'
import { TaskCard } from './TaskCard'

const COLUMNS: { id: TaskStatus; label: string }[] = [
  { id: 'todo', label: 'To Do' },
  { id: 'in_progress', label: 'In Progress' },
  { id: 'in_review', label: 'In Review' },
  { id: 'done', label: 'Done' },
]

export function KanbanBoard({
  tasks,
  assigneeNames,
  keepServerOrder,
  onStatusChange,
  onTaskClick,
}: {
  tasks: Task[]
  assigneeNames: Map<string, string>
  /** When the list was sorted by the server (not "board order"), keep that order in each column. */
  keepServerOrder: boolean
  onStatusChange: (taskId: string, status: TaskStatus) => void
  onTaskClick: (task: Task) => void
}) {
  const [activeTask, setActiveTask] = useState<Task | null>(null)
  // A small activation distance, not the default (0): without it, a plain
  // click to open the task detail panel gets swallowed as a zero-distance
  // drag instead of registering as a click.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 5 } }))

  function handleDragStart(event: DragStartEvent) {
    setActiveTask(tasks.find((t) => t.id === event.active.id) ?? null)
  }

  function handleDragEnd(event: DragEndEvent) {
    setActiveTask(null)
    const { active, over } = event
    if (!over) return

    const task = tasks.find((t) => t.id === active.id)
    if (!task) return

    // `over.id` is a column id when dropped on an empty column area, or
    // another task's id when dropped on top of a card — resolve either way
    // to the target column.
    const targetColumn =
      COLUMNS.find((c) => c.id === over.id)?.id ?? tasks.find((t) => t.id === over.id)?.status

    if (targetColumn && targetColumn !== task.status) {
      onStatusChange(task.id, targetColumn)
    }
  }

  return (
    <DndContext sensors={sensors} onDragStart={handleDragStart} onDragEnd={handleDragEnd}>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {COLUMNS.map((column) => (
          <KanbanColumn
            key={column.id}
            id={column.id}
            title={column.label}
            assigneeNames={assigneeNames}
            tasks={tasks
              .filter((t) => t.status === column.id)
              .sort((a, b) => (keepServerOrder ? 0 : a.position - b.position))}
            onTaskClick={onTaskClick}
          />
        ))}
      </div>
      <DragOverlay>
        {activeTask && (
          <TaskCard
            task={activeTask}
            assigneeName={activeTask.assignee_id ? assigneeNames.get(activeTask.assignee_id) : undefined}
            onClick={() => {}}
            dragging
          />
        )}
      </DragOverlay>
    </DndContext>
  )
}
