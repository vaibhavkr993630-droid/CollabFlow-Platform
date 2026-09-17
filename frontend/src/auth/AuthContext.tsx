import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import * as authApi from '../api/auth'
import { tokenStore } from '../api/tokenStore'
import type { User } from '../types'

interface AuthContextValue {
  user: User | null
  isLoading: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  // Starts true: on a fresh page load we don't yet know if the stored refresh
  // token is still valid, so routes must wait for that check rather than
  // flashing the login page before redirecting an already-authenticated user.
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    let cancelled = false

    async function restoreSession() {
      if (!tokenStore.getAccess() && !tokenStore.getRefresh()) {
        setIsLoading(false)
        return
      }
      try {
        const me = await authApi.fetchMe()
        if (!cancelled) setUser(me)
      } catch {
        // Access token expired and refresh failed (client.ts's interceptor
        // already cleared storage in that case) — just land on the login page.
        tokenStore.clear()
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    void restoreSession()
    return () => {
      cancelled = true
    }
  }, [])

  async function login(email: string, password: string) {
    const tokens = await authApi.login({ email, password })
    tokenStore.setPair(tokens.access_token, tokens.refresh_token)
    const me = await authApi.fetchMe()
    setUser(me)
  }

  async function register(email: string, password: string, fullName: string) {
    await authApi.register({ email, password, full_name: fullName })
    await login(email, password)
  }

  function logout() {
    tokenStore.clear()
    setUser(null)
  }

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
