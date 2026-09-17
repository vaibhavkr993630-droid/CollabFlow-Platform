// Tokens live in localStorage, not an httpOnly cookie — a deliberate, documented
// simplification (see README): it keeps the backend contract simple (no cookie
// handling), at the cost of tokens being readable by any script that runs on this
// origin (XSS risk). A production system would prefer httpOnly cookies for the
// refresh token specifically.
const ACCESS_KEY = 'collabflow.access_token'
const REFRESH_KEY = 'collabflow.refresh_token'

export const tokenStore = {
  getAccess: (): string | null => localStorage.getItem(ACCESS_KEY),
  getRefresh: (): string | null => localStorage.getItem(REFRESH_KEY),
  setPair: (access: string, refresh: string): void => {
    localStorage.setItem(ACCESS_KEY, access)
    localStorage.setItem(REFRESH_KEY, refresh)
  },
  setAccess: (access: string): void => {
    localStorage.setItem(ACCESS_KEY, access)
  },
  clear: (): void => {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}
