function normalizeBaseUrl(url?: string): string {
  if (!url) return ''
  let trimmed = url.trim().replace(/\/+$/, '')
  // Auto-prefix protocol if omitted (e.g., "api.autoheal.dev" -> "https://api.autoheal.dev")
  if (trimmed && !/^https?:\/\//i.test(trimmed)) {
    if (/^(localhost|127\.0\.0\.1)(:\d+)?$/i.test(trimmed)) {
      trimmed = `http://${trimmed}`
    } else {
      trimmed = `https://${trimmed}`
    }
  }
  if (trimmed.endsWith('/api/v1')) {
    trimmed = trimmed.slice(0, -7)
  } else if (trimmed.endsWith('/api')) {
    trimmed = trimmed.slice(0, -4)
  }
  return trimmed.replace(/\/+$/, '')
}

export const API_BASE_URL = normalizeBaseUrl(
  process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL
)
export const isApiConfigured = API_BASE_URL.length > 0
export const isDemoModeExplicit = process.env.NEXT_PUBLIC_DEMO_MODE === 'true'

// Demo mode is ONLY active when explicitly enabled or when no backend URL is set during local development.
// Production deployments must connect to a real backend and will never silently substitute mock data.
export const isDemoMode = isDemoModeExplicit || (!isApiConfigured && process.env.NODE_ENV === 'development')

const TOKEN_KEY = 'autoheal_access_token'
const USER_KEY = 'autoheal_user'

export function buildApiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`
  if (!API_BASE_URL) return cleanPath
  return `${API_BASE_URL}${cleanPath}`
}

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
  nullableNumbers?: readonly string[]
  booleans?: readonly string[]
}

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message)
    this.name = 'ApiError'
  }
}

// Refresh Token Rotation (RTR) Lock: Deduplicates concurrent refresh attempts to prevent replay-attack detection
let activeRefreshPromise: Promise<string | null> | null = null

async function performTokenRefresh(): Promise<string | null> {
  if (activeRefreshPromise) return activeRefreshPromise

  activeRefreshPromise = (async () => {
    try {
      const refreshRes = await fetch(buildApiUrl('/api/v1/auth/refresh'), {
        method: 'POST',
        headers: { Accept: 'application/json' },
        credentials: 'include',
      })
      if (refreshRes.ok) {
        const refreshData = await refreshRes.json()
        if (refreshData && refreshData.access_token) {
          setAccessToken(refreshData.access_token)
          if (refreshData.user) setStoredUser(refreshData.user)
          return refreshData.access_token as string
        }
      }
      setAccessToken(null)
      setStoredUser(null)
      return null
    } catch {
      setAccessToken(null)
      setStoredUser(null)
      return null
    } finally {
      activeRefreshPromise = null
    }
  })()

  return activeRefreshPromise
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!API_BASE_URL) {
    throw new ApiError('The FastAPI backend service is not configured. Set NEXT_PUBLIC_API_BASE_URL.', 0)
  }

  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.headers as Record<string, string> || {}),
  }

  const token = getAccessToken()
  if (token && !headers['Authorization']) {
    headers['Authorization'] = `Bearer ${token}`
  }

  // 15-second timeout guard if no custom signal is provided
  let timeoutId: ReturnType<typeof setTimeout> | undefined
  let signal = init.signal
  if (!signal && typeof AbortController !== 'undefined') {
    const controller = new AbortController()
    timeoutId = setTimeout(() => controller.abort(), 15000)
    signal = controller.signal
  }

  let response: Response
  try {
    response = await fetch(buildApiUrl(path), {
      cache: 'no-store',
      credentials: 'include',
      ...init,
      headers,
      signal,
    })
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') {
      throw new ApiError('Request timed out after 15 seconds.', 408)
    }
    throw new ApiError('Could not connect to the AutoHeal backend API. Verify the server is running and accessible.', 0)
  } finally {
    if (timeoutId) clearTimeout(timeoutId)
  }

  // Handle 401 token refresh with deduplicated RTR lock
  if (response.status === 401 && !path.startsWith('/api/v1/auth/')) {
    const newToken = await performTokenRefresh()
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`
      const retryRes = await fetch(buildApiUrl(path), {
        cache: 'no-store',
        credentials: 'include',
        ...init,
        headers,
        signal: init.signal,
      }).catch(() => null)

      if (retryRes && retryRes.ok) {
        return (await retryRes.json().catch(() => null)) as T
      }
      if (retryRes) {
        const retryBody = await retryRes.json().catch(() => null)
        const message = retryBody && typeof retryBody === 'object' && 'detail' in retryBody
          ? String(retryBody.detail)
          : `Request failed (${retryRes.status})`
        throw new ApiError(message, retryRes.status)
      }
    }
  }

  const body = await response.json().catch(() => null)

  if (!response.ok) {
    let message = `Request failed (${response.status})`
    if (body && typeof body === 'object') {
      if ('detail' in body) {
        message = Array.isArray(body.detail)
          ? body.detail.map((e: { msg?: string }) => e.msg || String(e)).join(', ')
          : String(body.detail)
      }
    }
    throw new ApiError(message, response.status)
  }

  return body as T
}

export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  if (!API_BASE_URL) throw new ApiError('The FastAPI backend service is not configured.', 0)
  const headers: Record<string, string> = {
    Accept: 'application/pdf, application/json, application/octet-stream',
  }
  const token = getAccessToken()
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  let response: Response
  try {
    response = await fetch(buildApiUrl(path), {
      cache: 'no-store',
      credentials: 'include',
      headers,
      signal,
    })
  } catch {
    throw new ApiError('Could not download file from AutoHeal backend.', 0)
  }

  if (response.status === 401 && !path.startsWith('/api/v1/auth/')) {
    const newToken = await performTokenRefresh()
    if (newToken) {
      headers['Authorization'] = `Bearer ${newToken}`
      response = await fetch(buildApiUrl(path), {
        cache: 'no-store',
        credentials: 'include',
        headers,
        signal,
      })
    }
  }

  if (!response.ok) {
    const text = await response.text().catch(() => '')
    let message = `Download failed (${response.status})`
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
  for (const field of shape.nullableNumbers ?? []) {
    if (record[field] !== null && record[field] !== undefined) {
      if (typeof record[field] !== 'number' || !Number.isFinite(record[field])) {
        throw new ApiError(`The ${resource} response is missing a valid ${field}.`, 502)
      }
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
