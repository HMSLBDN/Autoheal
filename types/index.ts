export type ServiceStatus = 'healthy' | 'degraded' | 'critical'
export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type IncidentStatus = 'open' | 'investigating' | 'recovering' | 'resolved'
export type RecoveryStatus = 'pending_approval' | 'approved' | 'running' | 'completed' | 'failed'

export interface Service {
  id: string
  name: string
  environment: string
  status: ServiceStatus
  availability: number
  errorRate: number
  latencyMs: number
  lastChecked: string
}

export interface ServiceMetrics {
  serviceId: string
  sampledAt: string
  cpuPercent: number
  memoryPercent: number
  requestRate: number
  errorRate: number
  latencyMs: number
  availability: number
  history: Array<{ time: string; value: number }>
}

export interface IncidentEvidence {
  id: string
  kind: 'metric' | 'log' | 'deployment' | 'health_check'
  title: string
  detail: string
  timestamp: string
}

export interface IncidentEvent {
  id: string
  label: string
  detail: string
  timestamp: string
  tone: 'neutral' | 'warning' | 'success'
}

export interface Incident {
  id: string
  serviceId: string
  serviceName: string
  title: string
  severity: Severity
  status: IncidentStatus
  detectedAt: string
  recoveryStatus: string
  errorRate: number
  threshold: number
  probableCause: string
  recommendedAction: string
  evidence: IncidentEvidence[]
  events: IncidentEvent[]
}

export interface RecoveryResult {
  verified: boolean
  summary: string
  completedAt: string
}

export interface RecoveryAction {
  id: string
  incidentId: string
  serviceName: string
  action: string
  status: RecoveryStatus
  approvalRequired: boolean
  requestedBy: string
  requestedAt: string
  durationSeconds?: number
  verification: 'pending' | 'passed' | 'failed' | 'not_started'
  result?: RecoveryResult
}

export interface AnalyticsSummary {
  detectionLatencySeconds: number
  recoveryDurationMinutes: number
  recoverySuccessRate: number
  falsePositiveRate: number
  availability: number
  incidentCount: number
  history: Array<{ date: string; incidents: number; recoveries: number; availability: number }>
}
