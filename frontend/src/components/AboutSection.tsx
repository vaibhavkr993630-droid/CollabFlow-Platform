const REPO_URL = 'https://github.com/vaibhavkr993630-droid/CollabFlow-Platform'

const FEATURES: { title: string; body: string }[] = [
  {
    title: 'Live Kanban board',
    body: 'Drag tasks across To Do, In Progress, In Review and Done. Every change from a teammate — a status move, a new comment, an attachment — appears on your screen instantly, no refreshing.',
  },
  {
    title: 'Teams, roles & invites',
    body: 'Organize work into Organizations, Workspaces and Projects. Invite teammates by email and control what they can do with Owner, Admin and Member roles.',
  },
  {
    title: 'Everything a task needs',
    body: 'Assign work, set priorities and due dates, add labels, break work into subtasks, attach files, and discuss right on the task with comments and @mentions.',
  },
  {
    title: 'Stay notified',
    body: "Get notified the moment you're mentioned, assigned a task, invited somewhere, or a deadline is coming up — in the app and by email.",
  },
  {
    title: 'Find anything, track everything',
    body: 'Search and filter the board by assignee, label or priority, sort it your way, and look back at a full history of everything that happened on a project.',
  },
  {
    title: 'Secure by default',
    body: 'Safe sign-in, and a self-service "forgot password" flow that emails you a one-time link to reset it.',
  },
]

/**
 * Shown only while the dashboard has nothing else to show (no workspace
 * selected yet) — see DashboardPage. The point is to give a first-time
 * visitor (an interviewer, a recruiter) something to read instead of three
 * near-empty columns; the moment there's real content on screen (a
 * workspace's members), this steps aside rather than competing with it.
 *
 * Deliberately free of implementation terms (no "WebSocket", "Redis",
 * "FastAPI", ...) — this is what the app does for the person using it, not
 * how it's built. That belongs in the README, for whoever reads the code.
 */
export function AboutSection() {
  return (
    <section className="mt-6 rounded-xl border border-gray-200 bg-white p-6">
      <h2 className="text-base font-semibold text-brand-600">About CollabFlow</h2>
      <p className="mt-1 mb-5 max-w-2xl text-sm text-gray-500">
        Plan work, track progress and stay in sync with your team — all in one place, updating
        live as things happen.
      </p>

      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
        {FEATURES.map((feature) => (
          <div key={feature.title} className="flex gap-2.5">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-brand-500" />
            <div>
              <h3 className="text-sm font-medium text-gray-700">{feature.title}</h3>
              <p className="mt-0.5 text-sm text-gray-500">{feature.body}</p>
            </div>
          </div>
        ))}
      </div>

      <p className="mt-6 border-t border-gray-100 pt-4 text-xs text-gray-400">
        Built by{' '}
        <a
          href={REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="font-medium text-brand-600 hover:underline"
        >
          Vaibhav Kumar · GitHub
        </a>
      </p>
    </section>
  )
}
