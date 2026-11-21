import type {
  AgentCertificate,
  AnalyticsSummary,
  Anomaly,
  DeploymentImpact,
  EscalationEvent,
  EscalationPolicy,
  IdentityProvider,
  Incident,
  IncidentAnalysis,
  IncidentAssignment,
  IncidentComment,
  IncidentCorrelationGroup,
  IncidentEvent,
  IncidentEvidence,
  InfrastructureAgent,
  IntelligenceOverview,
  ModelEvaluationMetric,
  NotificationChannel,
  NotificationDelivery,
  NotificationSubscription,
  ObservabilityMetrics,
  Prediction,
  PreventiveRecommendation,
  RecoveryAction,
  RecoveryPolicy,
  ReleaseEvaluation,
  SecurityAuditEvent,
  SecurityAuditSummary,
  Service,
  ServiceMetrics,
  ServiceRisk,
  TimelineItem,
  TraceSpan,
  UnifiedTimeline,
  UserSession,
  WebhookDeliveryAttempt,
  WebhookEndpoint,
} from '@/types'
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
    numbers: ['detectionLatencySeconds', 'recoveryDurationMinutes', 'recoverySuccessRate', 'availability', 'incidentCount'],
    nullableNumbers: ['falsePositiveRate', 'operatorRejectionRate'],
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
  async downloadReport(id: string, format: 'pdf' | 'json' = 'pdf', signal?: AbortSignal) {
    return apiBlob(`/api/v1/incidents/${encodeURIComponent(id)}/report?format=${format}`, signal)
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

export type WorkspaceSettings = {
  organization: {
    id: string
    slug: string
    name: string
    plan: string
    is_active: boolean
  }
  user: AuthUser
  environment: {
    app_env: string
    ai_provider: string
    monitoring_interval_seconds: number
    max_recovery_retries: number
    recovery_cooldown_seconds: number
  }
}

export const settingsApi = {
  async get(signal?: AbortSignal): Promise<WorkspaceSettings> {
    return apiRequest<WorkspaceSettings>('/api/v1/settings', { signal })
  },
  async update(payload: { full_name?: string; organization_name?: string }): Promise<WorkspaceSettings> {
    return apiRequest<WorkspaceSettings>('/api/v1/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
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

function validateAgent(value: unknown): InfrastructureAgent {
  const agent = asObject<InfrastructureAgent>(value, 'infrastructure agent', {
    strings: ['id', 'organizationId', 'name', 'hostname', 'ipAddress', 'environment', 'status', 'version', 'publicKeyFingerprint', 'lastHeartbeat', 'createdAt'],
  })
  if (!['online', 'busy', 'degraded', 'offline', 'revoked'].includes(agent.status)) {
    throw new ApiError('The agent response contains an unsupported status.', 502)
  }
  if (!Array.isArray(agent.capabilities)) {
    agent.capabilities = ['restart_service', 'health_check']
  }
  return agent
}

function validatePolicy(value: unknown): RecoveryPolicy {
  return asObject<RecoveryPolicy>(value, 'recovery policy', {
    strings: ['id', 'serviceId', 'action'],
    booleans: ['approvalRequired', 'isActive'],
    numbers: ['cooldownSeconds', 'maxRetries'],
  })
}

export const agentsApi = {
  async list(signal?: AbortSignal): Promise<InfrastructureAgent[]> {
    return asArray<InfrastructureAgent>(await apiRequest<unknown>('/api/v1/agents', { signal }), 'agents', validateAgent)
  },
  async get(id: string, signal?: AbortSignal): Promise<InfrastructureAgent> {
    return validateAgent(await apiRequest<unknown>(`/api/v1/agents/${encodeURIComponent(id)}`, { signal }))
  },
  async register(payload: { name: string; hostname: string; ip_address: string; environment?: string; capabilities?: string[] }): Promise<{ agent: InfrastructureAgent; agent_secret: string }> {
    return apiRequest<{ agent: InfrastructureAgent; agent_secret: string }>('/api/v1/agents/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async revoke(id: string): Promise<{ message: string; status: string }> {
    return apiRequest<{ message: string; status: string }>(`/api/v1/agents/${encodeURIComponent(id)}/revoke`, {
      method: 'POST',
    })
  },
}

export const policiesApi = {
  async list(signal?: AbortSignal): Promise<RecoveryPolicy[]> {
    return asArray<RecoveryPolicy>(await apiRequest<unknown>('/api/v1/policies', { signal }), 'policies', validatePolicy)
  },
  async forService(serviceId: string, signal?: AbortSignal): Promise<RecoveryPolicy[]> {
    return asArray<RecoveryPolicy>(await apiRequest<unknown>(`/api/v1/policies/${encodeURIComponent(serviceId)}`, { signal }), 'service policies', validatePolicy)
  },
  async update(serviceId: string, payload: { approval_required?: boolean; cooldown_seconds?: number; max_retries?: number; is_active?: boolean }, action = 'restart_service'): Promise<RecoveryPolicy> {
    return validatePolicy(await apiRequest<unknown>(`/api/v1/policies/${encodeURIComponent(serviceId)}?action=${encodeURIComponent(action)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }))
  },
  async evaluate(serviceId: string, action: string, agentId?: string): Promise<{ allowed: boolean; requiresApproval: boolean; reason: string; cooldownRemainingSeconds: number; retryCount: number; maxRetries: number }> {
    return apiRequest<{ allowed: boolean; requiresApproval: boolean; reason: string; cooldownRemainingSeconds: number; retryCount: number; maxRetries: number }>('/api/v1/policies/evaluate/check', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ service_id: serviceId, action, agent_id: agentId }),
    })
  },
}

export const intelligenceApi = {
  async overview(signal?: AbortSignal): Promise<IntelligenceOverview> {
    return apiRequest<IntelligenceOverview>('/api/v1/intelligence/overview', { signal })
  },
  async predictions(serviceId?: string, signal?: AbortSignal): Promise<Prediction[]> {
    const query = serviceId ? `?service_id=${encodeURIComponent(serviceId)}` : ''
    return apiRequest<Prediction[]>(`/api/v1/intelligence/predictions${query}`, { signal })
  },
  async anomalies(serviceId?: string, status?: string, signal?: AbortSignal): Promise<Anomaly[]> {
    const params = new URLSearchParams()
    if (serviceId) params.append('service_id', serviceId)
    if (status) params.append('status', status)
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiRequest<Anomaly[]>(`/api/v1/intelligence/anomalies${query}`, { signal })
  },
  async riskScores(signal?: AbortSignal): Promise<ServiceRisk[]> {
    return apiRequest<ServiceRisk[]>('/api/v1/intelligence/risk-scores', { signal })
  },
  async serviceRisk(serviceId: string, signal?: AbortSignal): Promise<ServiceRisk> {
    return apiRequest<ServiceRisk>(`/api/v1/intelligence/risk-scores/${encodeURIComponent(serviceId)}`, { signal })
  },
  async correlations(incidentId?: string, signal?: AbortSignal): Promise<IncidentCorrelationGroup[]> {
    const path = incidentId
      ? `/api/v1/intelligence/correlations/${encodeURIComponent(incidentId)}`
      : '/api/v1/intelligence/correlations'
    return apiRequest<IncidentCorrelationGroup[]>(path, { signal })
  },
  async deploymentImpact(serviceId: string, signal?: AbortSignal): Promise<DeploymentImpact> {
    return apiRequest<DeploymentImpact>(`/api/v1/intelligence/deployment-impact/${encodeURIComponent(serviceId)}`, { signal })
  },
  async preventiveRecommendations(serviceId?: string, status?: string, signal?: AbortSignal): Promise<PreventiveRecommendation[]> {
    const params = new URLSearchParams()
    if (serviceId) params.append('service_id', serviceId)
    if (status) params.append('status', status)
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiRequest<PreventiveRecommendation[]>(`/api/v1/intelligence/preventive-recommendations${query}`, { signal })
  },
  async updateRecommendationStatus(id: string, status: string): Promise<PreventiveRecommendation> {
    return apiRequest<PreventiveRecommendation>(`/api/v1/intelligence/preventive-recommendations/${encodeURIComponent(id)}/status`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    })
  },
  async incidentAnalysis(incidentId: string, signal?: AbortSignal): Promise<IncidentAnalysis> {
    return apiRequest<IncidentAnalysis>(`/api/v1/intelligence/incident-analysis/${encodeURIComponent(incidentId)}`, { signal })
  },
  async modelEvaluations(signal?: AbortSignal): Promise<ModelEvaluationMetric[]> {
    return apiRequest<ModelEvaluationMetric[]>('/api/v1/intelligence/model-evaluation', { signal })
  },
}


export const notificationsApi = {
  async listChannels(signal?: AbortSignal): Promise<NotificationChannel[]> {
    return apiRequest<NotificationChannel[]>('/api/v1/notifications/channels', { signal })
  },
  async createChannel(payload: { name: string; channelType: string; isEnabled?: boolean; config: Record<string, any>; secretToken?: string; rateLimitPerMinute?: number }): Promise<NotificationChannel> {
    return apiRequest<NotificationChannel>('/api/v1/notifications/channels', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async updateChannel(id: string, payload: Partial<{ name: string; isEnabled: boolean; config: Record<string, any>; secretToken: string; rateLimitPerMinute: number }>): Promise<NotificationChannel> {
    return apiRequest<NotificationChannel>(`/api/v1/notifications/channels/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async deleteChannel(id: string): Promise<void> {
    await apiRequest<void>(`/api/v1/notifications/channels/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },
  async testChannel(id: string, message?: string): Promise<{ deliveryId: string; status: string; detail: string }> {
    return apiRequest<{ deliveryId: string; status: string; detail: string }>(`/api/v1/notifications/channels/${encodeURIComponent(id)}/test`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
  },
  async listSubscriptions(signal?: AbortSignal): Promise<NotificationSubscription[]> {
    return apiRequest<NotificationSubscription[]>('/api/v1/notifications/subscriptions', { signal })
  },
  async createSubscription(payload: { channelId: string; eventType: string; minSeverity?: string; isActive?: boolean }): Promise<NotificationSubscription> {
    return apiRequest<NotificationSubscription>('/api/v1/notifications/subscriptions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async listDeliveries(channelId?: string, status?: string, signal?: AbortSignal): Promise<NotificationDelivery[]> {
    const params = new URLSearchParams()
    if (channelId) params.append('channel_id', channelId)
    if (status) params.append('status', status)
    const query = params.toString() ? `?${params.toString()}` : ''
    return apiRequest<NotificationDelivery[]>(`/api/v1/notifications/deliveries${query}`, { signal })
  },
  async retryDelivery(deliveryId: string): Promise<NotificationDelivery> {
    return apiRequest<NotificationDelivery>(`/api/v1/notifications/deliveries/${encodeURIComponent(deliveryId)}/retry`, {
      method: 'POST',
    })
  },
}

export const webhooksApi = {
  async listEndpoints(signal?: AbortSignal): Promise<WebhookEndpoint[]> {
    return apiRequest<WebhookEndpoint[]>('/api/v1/webhooks/endpoints', { signal })
  },
  async createEndpoint(payload: { name: string; targetUrl: string; secretToken?: string; isActive?: boolean; events?: string[]; timeoutSeconds?: number }): Promise<WebhookEndpoint> {
    return apiRequest<WebhookEndpoint>('/api/v1/webhooks/endpoints', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async getEndpoint(id: string, signal?: AbortSignal): Promise<WebhookEndpoint> {
    return apiRequest<WebhookEndpoint>(`/api/v1/webhooks/endpoints/${encodeURIComponent(id)}`, { signal })
  },
  async updateEndpoint(id: string, payload: Partial<{ name: string; targetUrl: string; secretToken: string; isActive: boolean; events: string[]; timeoutSeconds: number }>): Promise<WebhookEndpoint> {
    return apiRequest<WebhookEndpoint>(`/api/v1/webhooks/endpoints/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async deleteEndpoint(id: string): Promise<void> {
    await apiRequest<void>(`/api/v1/webhooks/endpoints/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },
  async listDeliveries(endpointId: string, signal?: AbortSignal): Promise<WebhookDeliveryAttempt[]> {
    return apiRequest<WebhookDeliveryAttempt[]>(`/api/v1/webhooks/endpoints/${encodeURIComponent(endpointId)}/deliveries`, { signal })
  },
  async verifySignature(payload: { secret: string; signature: string; timestamp: string; payload: Record<string, any>; max_skew_seconds?: number }): Promise<{ is_valid: boolean; detail: string }> {
    return apiRequest<{ is_valid: boolean; detail: string }>('/api/v1/webhooks/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
}

export const collaborationApi = {
  async listComments(incidentId: string, signal?: AbortSignal): Promise<IncidentComment[]> {
    return apiRequest<IncidentComment[]>(`/api/v1/incidents/${encodeURIComponent(incidentId)}/comments`, { signal })
  },
  async createComment(incidentId: string, content: string, commentType = 'comment'): Promise<IncidentComment> {
    return apiRequest<IncidentComment>(`/api/v1/incidents/${encodeURIComponent(incidentId)}/comments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, commentType }),
    })
  },
  async getAssignment(incidentId: string, signal?: AbortSignal): Promise<IncidentAssignment | null> {
    return apiRequest<IncidentAssignment | null>(`/api/v1/incidents/${encodeURIComponent(incidentId)}/assignment`, { signal })
  },
  async assignIncident(incidentId: string, assignedToName: string, assignedToUserId?: string): Promise<IncidentAssignment> {
    return apiRequest<IncidentAssignment>(`/api/v1/incidents/${encodeURIComponent(incidentId)}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ assignedToName, assignedToUserId }),
    })
  },
  async acknowledgeIncident(incidentId: string, note?: string): Promise<{ status: string; incident_id: string; incident_status: string; acknowledged_by: string }> {
    return apiRequest<{ status: string; incident_id: string; incident_status: string; acknowledged_by: string }>(`/api/v1/incidents/${encodeURIComponent(incidentId)}/acknowledge`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ note }),
    })
  },
  async escalateIncident(incidentId: string, reason: string, targetLevel?: number): Promise<EscalationEvent> {
    return apiRequest<EscalationEvent>(`/api/v1/incidents/${encodeURIComponent(incidentId)}/escalate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason, targetLevel }),
    })
  },
}

export const escalationsApi = {
  async listPolicies(signal?: AbortSignal): Promise<EscalationPolicy[]> {
    return apiRequest<EscalationPolicy[]>('/api/v1/escalations/policies', { signal })
  },
  async createPolicy(payload: Partial<EscalationPolicy>): Promise<EscalationPolicy> {
    return apiRequest<EscalationPolicy>('/api/v1/escalations/policies', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async getPolicy(id: string, signal?: AbortSignal): Promise<EscalationPolicy> {
    return apiRequest<EscalationPolicy>(`/api/v1/escalations/policies/${encodeURIComponent(id)}`, { signal })
  },
  async updatePolicy(id: string, payload: Partial<EscalationPolicy>): Promise<EscalationPolicy> {
    return apiRequest<EscalationPolicy>(`/api/v1/escalations/policies/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async deletePolicy(id: string): Promise<void> {
    await apiRequest<void>(`/api/v1/escalations/policies/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },
  async triggerEvaluation(): Promise<EscalationEvent[]> {
    return apiRequest<EscalationEvent[]>('/api/v1/escalations/evaluate', {
      method: 'POST',
    })
  },
  async listEvents(incidentId?: string, signal?: AbortSignal): Promise<EscalationEvent[]> {
    const query = incidentId ? `?incident_id=${encodeURIComponent(incidentId)}` : ''
    return apiRequest<EscalationEvent[]>(`/api/v1/escalations/events${query}`, { signal })
  },
}

export const releasesApi = {
  async listEvaluations(serviceId?: string, signal?: AbortSignal): Promise<ReleaseEvaluation[]> {
    const query = serviceId ? `?service_id=${encodeURIComponent(serviceId)}` : ''
    return apiRequest<ReleaseEvaluation[]>(`/api/v1/releases/evaluations${query}`, { signal })
  },
  async evaluateCanary(payload: { serviceId: string; releaseTag: string; trafficPercentage?: number; observationWindowMinutes?: number; thresholds?: Record<string, number> }): Promise<ReleaseEvaluation> {
    return apiRequest<ReleaseEvaluation>('/api/v1/releases/evaluate-canary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async getEvaluation(id: string, signal?: AbortSignal): Promise<ReleaseEvaluation> {
    return apiRequest<ReleaseEvaluation>(`/api/v1/releases/evaluations/${encodeURIComponent(id)}`, { signal })
  },
}

export const timelineApi = {
  async getTimeline(serviceId?: string, signal?: AbortSignal): Promise<UnifiedTimeline> {
    const query = serviceId ? `?serviceId=${encodeURIComponent(serviceId)}` : ''
    return apiRequest<UnifiedTimeline>(`/api/v1/timeline${query}`, { signal })
  },
}

// ==============================================================================
// Phase 10: Enterprise SSO, Sessions, Observability, and mTLS APIs
// ==============================================================================

export const ssoApi = {
  async listProviders(signal?: AbortSignal): Promise<IdentityProvider[]> {
    return apiRequest<IdentityProvider[]>('/api/v1/auth/sso/providers', { signal })
  },
  async createProvider(payload: {
    name: string
    idp_type?: string
    issuer_url: string
    client_id: string
    client_secret: string
    metadata_url?: string
    role_mapping_json?: Record<string, any>
    allowed_domains?: string[]
    is_active?: boolean
    is_enforced?: boolean
  }): Promise<IdentityProvider> {
    return apiRequest<IdentityProvider>('/api/v1/auth/sso/providers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async updateProvider(id: string, payload: Partial<IdentityProvider>): Promise<IdentityProvider> {
    return apiRequest<IdentityProvider>(`/api/v1/auth/sso/providers/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
  async deleteProvider(id: string): Promise<void> {
    await apiRequest<void>(`/api/v1/auth/sso/providers/${encodeURIComponent(id)}`, {
      method: 'DELETE',
    })
  },
  async initiateAuthorize(providerId: string, redirectUri: string): Promise<{ authorization_url: string; state: string; code_verifier: string }> {
    return apiRequest<{ authorization_url: string; state: string; code_verifier: string }>('/api/v1/auth/sso/authorize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: providerId, redirect_uri: redirectUri }),
    })
  },
  async handleCallback(payload: {
    provider_id: string
    code: string
    state: string
    code_verifier: string
    redirect_uri: string
  }): Promise<any> {
    return apiRequest<any>('/api/v1/auth/sso/callback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
  },
}

export const sessionsApi = {
  async listSessions(signal?: AbortSignal): Promise<UserSession[]> {
    return apiRequest<UserSession[]>('/api/v1/auth/sessions', { signal })
  },
  async revokeSession(sessionId: string, reason?: string): Promise<void> {
    await apiRequest<void>(`/api/v1/auth/sessions/${encodeURIComponent(sessionId)}/revoke`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
  },
  async revokeAllSessions(keepCurrent: boolean = true): Promise<{ revoked_sessions_count: number }> {
    return apiRequest<{ revoked_sessions_count: number }>(`/api/v1/auth/sessions/revoke-all?keep_current=${keepCurrent}`, {
      method: 'POST',
    })
  },
  async listSecurityEvents(limit: number = 50, signal?: AbortSignal): Promise<SecurityAuditEvent[]> {
    return apiRequest<SecurityAuditEvent[]>(`/api/v1/auth/security/audit-events?limit=${limit}`, { signal })
  },
  async getSecuritySummary(signal?: AbortSignal): Promise<SecurityAuditSummary> {
    return apiRequest<SecurityAuditSummary>('/api/v1/auth/security/audit-summary', { signal })
  },
}

export const observabilityApi = {
  async getStats(signal?: AbortSignal): Promise<{ status: string; data: ObservabilityMetrics }> {
    return apiRequest<{ status: string; data: ObservabilityMetrics }>('/api/v1/observability/stats', { signal })
  },
  async getTraces(limit: number = 50, signal?: AbortSignal): Promise<{ status: string; count: number; traces: TraceSpan[] }> {
    return apiRequest<{ status: string; count: number; traces: TraceSpan[] }>(`/api/v1/observability/traces?limit=${limit}`, { signal })
  },
  async getMetricsText(signal?: AbortSignal): Promise<string> {
    const res = await fetch('/api/v1/observability/metrics', { signal })
    return res.text()
  },
}

export const agentCertApi = {
  async issueCert(agentId: string, validDays: number = 365, commonName?: string): Promise<AgentCertificate & { private_key_pem?: string; ca_cert_pem: string }> {
    return apiRequest<AgentCertificate & { private_key_pem?: string; ca_cert_pem: string }>(`/api/v1/agents/${encodeURIComponent(agentId)}/cert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ agent_id: agentId, valid_days: validDays, common_name: commonName }),
    })
  },
  async getCert(agentId: string, signal?: AbortSignal): Promise<AgentCertificate> {
    return apiRequest<AgentCertificate>(`/api/v1/agents/${encodeURIComponent(agentId)}/cert`, { signal })
  },
  async revokeCert(agentId: string, reason?: string): Promise<void> {
    await apiRequest<void>(`/api/v1/agents/${encodeURIComponent(agentId)}/revoke-cert`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason }),
    })
  },
  async verifyMtls(agentId: string): Promise<{ status: string; is_valid: boolean; details: any }> {
    return apiRequest<{ status: string; is_valid: boolean; details: any }>(`/api/v1/agents/${encodeURIComponent(agentId)}/verify-mtls`, {
      method: 'POST',
    })
  },
}

