import type { AnalyticsSummary, Incident, IncidentEvent, IncidentEvidence, RecoveryAction, Service, ServiceMetrics } from '@/types'
import { apiBlob, apiRequest, asArray, asObject, ApiError, AuthUser, setAccessToken, setStoredUser } from './client'

function validateService(value: unknown): Service {
  const service = asObject<Service>(value, 'service', {
    strings: ['id', 'name', 'environment', 'status', 'lastChecked'],
    numbers: ['availability', 'errorRate', 'latencyMs'],
  })
  if (!['healthy', 'degraded', 'critical'].includes(service.status)) throw new ApiError('The service response contains an unsupported status.', 502)
  return service
}

function validateMetrics(value: unknown): ServiceMetrics {
  const metrics = asObject<ServiceMetrics>(value, 'service metrics', {
    strings: ['serviceId', 'sampledAt'],
    numbers: ['cpuPercent', 'memoryPercent', 'requestRate', 'errorRate', 'latencyMs', 'availability'],
  })
  if (!Array.isArray(metrics.history)) throw new ApiError('The service metrics response is missing a history series.', 502)
  metrics.history = metrics.history.map((point) => asObject<{ time: string; value: number }>(point, 'service metric history', { strings: ['time'], numbers: ['value'] }))
  return metrics
}

function validateEvidence(value: unknown): IncidentEvidence {
  const evidence = asObject<IncidentEvidence>(value, 'incident evidence', {
    strings: ['id', 'kind', 'title', 'detail', 'timestamp'],
  })
  if (!['metric', 'log', 'deployment', 'health_check'].includes(evidence.kind)) throw new ApiError('The incident evidence contains an unsupported kind.', 502)
  return evidence
}

function validateEvent(value: unknown): IncidentEvent {
  const event = asObject<IncidentEvent>(value, 'incident event', {
    strings: ['id', 'label', 'detail', 'timestamp', 'tone'],
  })
  if (!['neutral', 'warning', 'success'].includes(event.tone)) throw new ApiError('The incident event contains an unsupported tone.', 502)
  return event
}

function validateIncident(value: unknown): Incident {
  const incident = asObject<Incident>(value, 'incident', {
    strings: ['id', 'serviceId', 'serviceName', 'title', 'severity', 'status', 'detectedAt', 'recoveryStatus', 'probableCause', 'recommendedAction'],
    numbers: ['errorRate', 'threshold'],
  })
  if (!['critical', 'high', 'medium', 'low'].includes(incident.severity)) throw new ApiError('The incident contains an unsupported severity.', 502)
  if (!['open', 'investigating', 'recovering', 'resolved'].includes(incident.status)) throw new ApiError('The incident contains an unsupported status.', 502)
  return {
    ...incident,
    evidence: asArray<IncidentEvidence>(incident.evidence, 'incident evidence', validateEvidence),
    events: asArray<IncidentEvent>(incident.events, 'incident events', validateEvent),
  }
}

function validateRecovery(value: unknown): RecoveryAction {
  const action = asObject<RecoveryAction>(value, 'recovery action', {
    strings: ['id', 'incidentId', 'serviceName', 'action', 'status', 'requestedBy', 'requestedAt', 'verification'],
    booleans: ['approvalRequired'],
  })
  if (!['pending_approval', 'approved', 'running', 'completed', 'failed', 'rejected'].includes(action.status)) throw new ApiError('The recovery response contains an unsupported status.', 502)
  if (!['pending', 'passed', 'failed', 'not_started'].includes(action.verification)) throw new ApiError('The recovery response contains an unsupported verification state.', 502)
  if (action.durationSeconds !== undefined && (typeof action.durationSeconds !== 'number' || !Number.isFinite(action.durationSeconds))) throw new ApiError('The recovery response contains an invalid duration.', 502)
  return action
}

function validateAnalytics(value: unknown): AnalyticsSummary {
  const summary = asObject<AnalyticsSummary>(value, 'analytics', {
    numbers: ['detectionLatencySeconds', 'recoveryDurationMinutes', 'recoverySuccessRate', 'falsePositiveRate', 'availability', 'incidentCount'],
  })
  return {
    ...summary,
    history: asArray<AnalyticsSummary['history'][number]>(summary.history, 'analytics history', (point) => asObject(point, 'analytics history item', {
      strings: ['date'],
      numbers: ['incidents', 'recoveries', 'availability'],
    })),
  }
}

export const healthApi = {
  async get(signal?: AbortSignal) {
    return asObject<{ status: string; timestamp?: string }>(await apiRequest<unknown>('/api/v1/health', { signal }), 'health', { strings: ['status'] })
  },
}

export const servicesApi = {
  async list(signal?: AbortSignal) {
    return asArray<Service>(await apiRequest<unknown>('/api/v1/services', { signal }), 'services', validateService)
  },
  async metrics(id: string, signal?: AbortSignal) {
    return validateMetrics(await apiRequest<unknown>(`/api/v1/services/${encodeURIComponent(id)}/metrics`, { signal }))
  },
}

export const incidentsApi = {
  async list(signal?: AbortSignal) {
    return asArray<Incident>(await apiRequest<unknown>('/api/v1/incidents', { signal }), 'incidents', validateIncident)
  },
  async get(id: string, signal?: AbortSignal) {
    return validateIncident(await apiRequest<unknown>(`/api/v1/incidents/${encodeURIComponent(id)}`, { signal }))
  },
  async requestRecovery(id: string) {
    return validateRecovery(await apiRequest<unknown>(`/api/v1/incidents/${encodeURIComponent(id)}/recover`, { method: 'POST' }))
  },
  async downloadReport(id: string, signal?: AbortSignal) {
    return apiBlob(`/api/v1/incidents/${encodeURIComponent(id)}/report`, signal)
  },
}

export const recoveriesApi = {
  async list(signal?: AbortSignal) {
    return asArray<RecoveryAction>(await apiRequest<unknown>('/api/v1/recoveries', { signal }), 'recoveries', validateRecovery)
  },
  async approve(id: string) {
    return validateRecovery(await apiRequest<unknown>(`/api/v1/recoveries/${encodeURIComponent(id)}/approve`, { method: 'POST' }))
  },
  async execute(id: string) {
    return validateRecovery(await apiRequest<unknown>(`/api/v1/recoveries/${encodeURIComponent(id)}/execute`, { method: 'POST' }))
  },
  async reject(id: string, reason?: string) {
    return validateRecovery(await apiRequest<unknown>(`/api/v1/recoveries/${encodeURIComponent(id)}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    }))
  },
}

export const analyticsApi = {
  async summary(signal?: AbortSignal) {
    return validateAnalytics(await apiRequest<unknown>('/api/v1/analytics/summary', { signal }))
  },
}

export const alertsApi = {
  async sendWebhook(payload: unknown, secret?: string) {
    return apiRequest<{ status: string; processed_alerts: number; incidents_created: number; incidents_updated: number; details: string[] }>(
      '/api/v1/alerts/webhook',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Alertmanager-Secret': secret || 'autoheal_alertmanager_webhook_hmac_secret_key_12345',
        },
        body: JSON.stringify(payload),
      }
    )
  },
}

export type AuthResponse = {
  access_token: string
  token_type: string
  expires_in: number
  user: AuthUser
  refresh_token?: string
}

export const authApi = {
  async login(email: string, password: string): Promise<AuthResponse> {
    const data = await apiRequest<AuthResponse>('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    })
    if (data.access_token) {
      setAccessToken(data.access_token)
      if (data.user) setStoredUser(data.user)
    }
    return data
  },

  async register(email: string, password: string, fullName: string): Promise<AuthResponse> {
    const data = await apiRequest<AuthResponse>('/api/v1/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, full_name: fullName }),
    })
    if (data.access_token) {
      setAccessToken(data.access_token)
      if (data.user) setStoredUser(data.user)
    }
    return data
  },

  async logout(): Promise<void> {
    try {
      await apiRequest<{ message: string }>('/api/v1/auth/logout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    } finally {
      setAccessToken(null)
      setStoredUser(null)
    }
  },

  async me(signal?: AbortSignal): Promise<AuthUser> {
    const user = await apiRequest<AuthUser>('/api/v1/auth/me', { signal })
    if (user) setStoredUser(user)
    return user
  },

  async forgotPassword(email: string): Promise<{ message: string }> {
    return apiRequest<{ message: string }>('/api/v1/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email }),
    })
  },

  async resetPassword(token: string, newPassword: string): Promise<{ message: string }> {
    return apiRequest<{ message: string }>('/api/v1/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword }),
    })
  },
}
