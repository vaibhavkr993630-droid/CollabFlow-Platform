/**
 * Derives the WebSocket origin to connect to. In local dev, VITE_API_BASE_URL
 * is unset and Vite's dev proxy (vite.config.ts) forwards /ws to the backend
 * on the *same* origin the page is served from — window.location.host is
 * correct there. In production, the frontend (Vercel) and backend (Railway)
 * are on entirely different domains with no proxy between them, so this must
 * target VITE_API_BASE_URL instead — using window.location.host there would
 * silently try to open a WebSocket against the frontend's own static host,
 * which has no /ws route at all (this was live-broken in production until
 * caught by an actual browser test against the deployed site; a purely local
 * check never would have surfaced it, since local dev's proxy papers over the
 * exact distinction that matters here).
 */
export function wsBaseUrl(): string {
  const apiBase = import.meta.env.VITE_API_BASE_URL
  if (apiBase) {
    return apiBase.replace(/^http/, 'ws')
  }
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${protocol}://${window.location.host}`
}
