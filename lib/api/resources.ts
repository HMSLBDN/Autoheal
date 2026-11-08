import type { AnalyticsSummary, Incident, IncidentEvent, IncidentEvidence, RecoveryAction, Service, ServiceMetrics } from '@/types'
import { apiBlob, apiRequest, asArray, asObject, ApiError } from './client'

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
  if (!['pending_approval', 'approved', 'running', 'completed', 'failed'].includes(action.status)) throw new ApiError('The recovery response contains an unsupported status.', 502)
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
}

export const analyticsApi = {
  async summary(signal?: AbortSignal) {
    return validateAnalytics(await apiRequest<unknown>('/api/v1/analytics/summary', { signal }))
  },
}
