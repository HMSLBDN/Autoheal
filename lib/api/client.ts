export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, '') ?? ''
export const isApiConfigured = API_BASE_URL.length > 0

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

  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: 'no-store',
    ...init,
    headers: { Accept: 'application/json', ...init.headers },
    signal: init.signal,
  })
  const body = await response.json().catch(() => null)

  if (!response.ok) {
    const message = body && typeof body === 'object' && 'detail' in body ? String(body.detail) : `Request failed (${response.status})`
    throw new ApiError(message, response.status)
  }

  return body as T
}

export async function apiBlob(path: string, signal?: AbortSignal): Promise<Blob> {
  if (!API_BASE_URL) throw new ApiError('The FastAPI service is not configured.', 0)
  const response = await fetch(`${API_BASE_URL}${path}`, {
    cache: 'no-store',
    headers: { Accept: 'application/pdf, application/json, application/octet-stream' },
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
