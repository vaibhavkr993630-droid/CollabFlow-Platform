import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios'

import { tokenStore } from './tokenStore'

// Empty string in dev: Vite's proxy (vite.config.ts) forwards /api to the
// backend, so relative paths work without CORS. VITE_API_BASE_URL overrides
// this for production, where the frontend and backend are on different domains.
const baseURL = import.meta.env.VITE_API_BASE_URL ?? ''

export const apiClient = axios.create({ baseURL })

apiClient.interceptors.request.use((config) => {
  const token = tokenStore.getAccess()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

interface RetryableConfig extends InternalAxiosRequestConfig {
  _retried?: boolean
}

// Coalesces concurrent 401s into a single in-flight refresh call — several
// requests firing at once (e.g. a dashboard loading multiple resources) that
// all hit an expired access token should trigger exactly one refresh, not one
// per request racing to hit /api/auth/refresh simultaneously.
let refreshPromise: Promise<string> | null = null

async function refreshAccessToken(): Promise<string> {
  const refreshToken = tokenStore.getRefresh()
  if (!refreshToken) {
    throw new Error('No refresh token available')
  }
  const response = await axios.post<{ access_token: string }>(
    `${baseURL}/api/auth/refresh`,
    { refresh_token: refreshToken },
  )
  tokenStore.setAccess(response.data.access_token)
  return response.data.access_token
}

apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableConfig | undefined

    if (error.response?.status !== 401 || !originalRequest || originalRequest._retried) {
      return Promise.reject(error)
    }
    if (!tokenStore.getRefresh()) {
      return Promise.reject(error)
    }

    originalRequest._retried = true

    try {
      refreshPromise ??= refreshAccessToken().finally(() => {
        refreshPromise = null
      })
      const newAccessToken = await refreshPromise
      originalRequest.headers.Authorization = `Bearer ${newAccessToken}`
      return apiClient(originalRequest)
    } catch (refreshError) {
      tokenStore.clear()
      window.location.assign('/login')
      return Promise.reject(refreshError)
    }
  },
)
