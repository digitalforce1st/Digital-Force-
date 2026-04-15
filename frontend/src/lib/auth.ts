/**
 * Digital Force — Auth Utilities
 * JWT token management via localStorage.
 */

const TOKEN_KEY = 'df_token'
const USER_KEY = 'df_user'

export const getToken = (): string | null => {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export const setToken = (token: string): void => {
  localStorage.setItem(TOKEN_KEY, token)
}

export const clearToken = (): void => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

export const isAuthenticated = (): boolean => {
  return !!getToken()
}

export const setUser = (user: object): void => {
  localStorage.setItem(USER_KEY, JSON.stringify(user))
}

export const getUser = (): Record<string, string> | null => {
  if (typeof window === 'undefined') return null
  const u = localStorage.getItem(USER_KEY)
  if (!u) return null
  try { return JSON.parse(u) } catch { return null }
}

export const authHeaders = (): Record<string, string> => {
  const token = getToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
