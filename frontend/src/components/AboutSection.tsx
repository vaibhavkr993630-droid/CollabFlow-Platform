const FEATURES: { title: string; body: string }[] = [
  {
    title: 'Real-time boards',
    body: 'A drag-and-drop Kanban board that syncs over WebSockets — a status change, comment or attachment from a teammate appears instantly, with no refresh.',
  },
  {
    title: 'Teams & permissions',
    body: 'Organizations → Workspaces → Projects → Tasks, with Owner / Admin / Member roles enforced independently at both the workspace and the project level.',
  },
  {
    title: 'Full task detail',
    body: 'Assignees, priorities, due dates, labels, subtasks with progress, file attachments (S3-compatible storage, presigned downloads), and threaded comments with @mentions.',
  },
  {
    title: 'Notifications',
    body: 'In-app and email notifications for mentions, assignments, invites and due-soon reminders, delivered through a Celery + Redis background queue.',
  },
  {
    title: 'Search, filter & audit',
    body: 'Filter the board by assignee, label, priority or title, sort any way you like, and review a full activity feed of every change made to a project.',
  },
  {
    title: 'Secure accounts',
    body: 'JWT authentication with refresh tokens, live presence indicators, and self-service password reset via a signed, single-use emailed link.',
  },
]

const STACK = [
  'FastAPI',
  'Async SQLAlchemy',
  'PostgreSQL',
  'Redis',
  'WebSockets',
  'React 19 + TypeScript',
  'Docker',
  'CI/CD',
]

/**
 * Shown only while the dashboard has nothing else to show (no workspace
 * selected yet) — see DashboardPage. The point is to give a first-time
 * visitor (an interviewer, a recruiter) something to read instead of three
 * near-empty columns; the moment there's real content on screen (a
 * workspace's members), this steps aside rather than competing with it.
 */
export function AboutSection() {
  return (
    <section className="mt-6 rounded-xl border border-gray-200 bg-white p-6">
      <h2 className="text-base font-semibold text-gray-900">About CollabFlow</h2>
      <p className="mt-1 mb-5 max-w-2xl text-sm text-gray-500">
        A full-stack, real-time project-management platform built end to end — a focused hybrid
        of Jira's structured planning and Slack's live collaboration, from a from-scratch FastAPI
        + React codebase.
      </p>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {FEATURES.map((feature) => (
          <div key={feature.title}>
            <h3 className="text-sm font-medium text-gray-900">{feature.title}</h3>
            <p className="mt-0.5 text-sm text-gray-500">{feature.body}</p>
          </div>
        ))}
      </div>

      <div className="mt-6 flex flex-wrap gap-1.5 border-t border-gray-100 pt-4">
        {STACK.map((item) => (
          <span
            key={item}
            className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600"
          >
            {item}
          </span>
        ))}
      </div>
    </section>
  )
}
