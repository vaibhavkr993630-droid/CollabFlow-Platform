import { isAxiosError } from 'axios'

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export function timeAgo(iso: string): string {
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

/**
 * Turns whatever a failed request threw into a sentence a person can act on.
 * FastAPI puts a string in `detail` for our own errors ("No user found with
 * that email") and a list of field problems for validation errors (422).
 */
export function errorMessage(error: unknown, fallback = 'Something went wrong. Please try again.') {
  if (isAxiosError(error)) {
    if (!error.response) return "Can't reach the server. Check your connection and try again."
    const detail = error.response.data?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg)
    if (error.response.status === 403) return "You don't have permission to do that."
  }
  return fallback
}

/**
 * Activity summaries are written by the backend and end with the raw field
 * names that changed, e.g. "updated task 'X' (assignee_id, label_ids)". Show
 * those the way a person would say them: "(assignee, labels)".
 */
export function prettySummary(summary: string): string {
  return summary.replace(/\(([a-z_, ]+)\)$/, (_match, fields: string) =>
    `(${fields.replace(/_ids?\b/g, (m) => (m === '_ids' ? 's' : '')).replace(/_/g, ' ')})`,
  )
}
