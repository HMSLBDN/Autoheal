export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') ?? ''
export const isApiConfigured = API_BASE_URL.length > 0

const TOKEN_KEY = 'autoheal_access_token'
const USER_KEY = 'autoheal_user'

export type AuthUser = {
  id: string
  email: string
  full_name: string
  role: string
  organization_id: string
  organization_name?: string
  is_active: boolean
}

export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem(TOKEN_KEY)
}

export function setAccessToken(token: string | null): void {
  if (typeof window === 'undefined') return
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function getStoredUser(): AuthUser | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem(USER_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw) as AuthUser
  } catch {
    return null
  }
}

export function setStoredUser(user: AuthUser | null): void {
  if (typeof window === 'undefined') return
  if (user) {
    localStorage.setItem(USER_KEY, JSON.stringify(user))
  } else {
    localStorage.removeItem(USER_KEY)
  }
}

type ResponseShape = {
  strings?: readonly string[]
  numbers?: readonly string[]
  booleans?: readonly string[]
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE_URL) throw new ApiError('The FastAPI service is not configured.', 0)

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.headers as Record<string, string> || {}),
  }

  const token = getAccessToken()
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: 'no-store',
    credentials: 'include',
    ...init,
    headers,
    signal: init.signal,
  })

  // Handle 401 token refresh if we have a token and the path is not under /auth/
  if (response.status === 401 && !path.startsWith('/api/v1/auth/')) {
    try {
      const refreshRes = await fetch(`${API_BASE_URL}/api/v1/auth/refresh`, {
        method: 'POST',
        headers: { Accept: 'application/json' },
        credentials: 'include',
      })
      if (refreshRes.ok) {
        const refreshData = await refreshRes.json()
        if (refreshData && refreshData.access_token) {
          setAccessToken(refreshData.access_token)
          if (refreshData.user) setStoredUser(refreshData.user)
          headers['Authorization'] = `Bearer ${refreshData.access_token}`
          const retryRes = await fetch(`${API_BASE_URL}${path}`, {
            cache: 'no-store',
            credentials: 'include',
            ...init,
            headers,
            signal: init.signal,
          })
          const retryBody = await retryRes.json().catch(() => null)
          if (!retryRes.ok) {
            const message = retryBody && typeof retryBody === 'object' && 'detail' in retryBody ? String(retryBody.detail) : `Request failed (${retryRes.status})`
            throw new ApiError(message, retryRes.status)
          }
          return retryBody as T
        }
      } else {
        setAccessToken(null)
        setStoredUser(null)
      }
    } catch {
      setAccessToken(null)
      setStoredUser(null)
    }
  }

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    const message = body && typeof body === 'object' && 'detail' in body ? String(body.detail) : `Request failed (${response.status})`
    throw new ApiError(message, response.status)
  }

  return body as T
}

export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  if (!API_BASE_URL) throw new ApiError('The FastAPI service is not configured.', 0)
  const headers: Record<string, string> = {
    Accept: 'application/pdf, application/json, application/octet-stream',
  }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: 'no-store',
    credentials: 'include',
    headers,
    signal,
  })
  if (!response.ok) {
    const text = await response.text().catch(() => '')
    let message = `Request failed (${response.status})`
    try {
      const body = JSON.parse(text) as { detail?: unknown }
      if (body.detail) message = String(body.detail)
    } catch {}
    throw new ApiError(message, response.status)
  }
  return response.blob()
}

function unwrap(value: unknown): unknown {
  if (value && typeof value === 'object' && !Array.isArray(value) && 'data' in value) {
    return (value as { data: unknown }).data
  }
  return value
}

function assertShape(value: unknown, resource: string, shape: ResponseShape): Record<string, unknown> {
  const candidate = unwrap(value)
  if (!candidate || typeof candidate !== 'object' || Array.isArray(candidate)) {
    throw new ApiError(`The ${resource} response has an unexpected format.`, 502)
  }

  const record = candidate as Record<string, unknown>
  for (const field of shape.strings ?? []) {
    if (typeof record[field] !== 'string') throw new ApiError(`The ${resource} response is missing a valid ${field}.`, 502)
  }
  for (const field of shape.numbers ?? []) {
    if (typeof record[field] !== 'number' || !Number.isFinite(record[field])) {
      throw new ApiError(`The ${resource} response is missing a valid ${field}.`, 502)
    }
  }
  for (const field of shape.booleans ?? []) {
    if (typeof record[field] !== 'boolean') throw new ApiError(`The ${resource} response is missing a valid ${field}.`, 502)
  }
  return record
}

export function asArray<T>(value: unknown, resource: string, validate?: (item: unknown) => T): T[] {
  const candidate = unwrap(value)
  const items = candidate && typeof candidate === 'object' && !Array.isArray(candidate) && 'items' in candidate
    ? (candidate as { items: unknown }).items
    : candidate
  if (!Array.isArray(items)) throw new ApiError(`The ${resource} response has an unexpected format.`, 502)
  return validate ? items.map(validate) : items as T[]
}

export function asObject<T>(value: unknown, resource: string, shape: ResponseShape = {}): T {
  return assertShape(value, resource, shape) as T
}
