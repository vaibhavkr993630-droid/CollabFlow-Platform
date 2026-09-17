import { apiClient } from './client'
import type { User } from '../types'

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
}

export async function register(input: {
  email: string
  password: string
  full_name: string
}): Promise<User> {
  const { data } = await apiClient.post<User>('/api/auth/register', input)
  return data
}

export async function login(input: { email: string; password: string }): Promise<TokenPair> {
  const { data } = await apiClient.post<TokenPair>('/api/auth/login', input)
  return data
}

export async function fetchMe(): Promise<User> {
  const { data } = await apiClient.get<User>('/api/auth/me')
  return data
}
