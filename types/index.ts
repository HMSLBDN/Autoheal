export type ServiceStatus = 'healthy' | 'degraded' | 'critical'
export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type IncidentStatus = 'open' | 'investigating' | 'recovering' | 'resolved'
export type RecoveryStatus = 'pending_approval' | 'approved' | 'running' | 'completed' | 'failed' | 'rejected'

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
  falsePositiveRate: number | null
  operatorRejectionRate?: number
  availability: number
  incidentCount: number
  history: Array<{ date: string; incidents: number; recoveries: number; availability: number }>
}

export type AgentStatus = 'online' | 'busy' | 'degraded' | 'offline' | 'revoked'

export interface InfrastructureAgent {
  id: string
  organizationId?: string
  name: string
  hostname: string
  ipAddress: string
  environment: string
  status: AgentStatus
  version: string
  capabilities: string[]
  publicKeyFingerprint: string
  lastHeartbeat: string
  createdAt: string
}

export interface RecoveryPolicy {
  id: string
  serviceId: string
  action: string
  approvalRequired: boolean
  cooldownSeconds: number
  maxRetries: number
  isActive: boolean
}

// Phase 8 AI Intelligence & Predictive Monitoring Types
export interface Anomaly {
  id: string
  organizationId: string
  serviceId: string
  serviceName: string
  metricName: string
  currentValue: number
  baselineValue: number
  zScore: number
  anomalyScore: number
  severity: 'informational' | 'low' | 'medium' | 'high' | 'critical'
  status: 'detected' | 'correlated' | 'resolved' | 'suppressed'
  details: string
  detectedAt: string
  createdAt: string
}

export interface Prediction {
  id: string
  organizationId: string
  serviceId: string
  serviceName: string
  metricName: string
  currentValue: number
  predictedValue: number
  thresholdValue: number
  predictionHorizonMinutes: number
  riskLevel: 'informational' | 'low' | 'medium' | 'high' | 'critical'
  anomalyProbability: number
  algorithm: string
  supportingEvidence: string[]
  recommendedPreventiveAction: string
  predictedAt: string
  targetTime: string
}

export interface RiskFactor {
  factor: string
  weight: number
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
}

export interface ServiceRisk {
  id: string
  organizationId: string
  serviceId: string
  serviceName: string
  riskScore: number
  riskCategory: 'low' | 'moderate' | 'high' | 'critical'
  contributingFactors: RiskFactor[]
  cpuTrend: string
  memoryTrend: string
  incidentFrequency7d: number
  failedRecoveriesCount: number
  recentDeploymentFlag: boolean
  calculatedAt: string
}

export interface IncidentCorrelationItem {
  incidentId: string
  serviceName: string
  title: string
  severity: string
  status: string
  detectedAt: string
}

export interface IncidentCorrelationGroup {
  groupId: string
  primaryIncidentId: string
  correlationType: string
  correlationScore: number
  explanation: string
  sharedEvidence: string[]
  incidents: IncidentCorrelationItem[]
  createdAt: string
}

export interface DeploymentImpact {
  serviceId: string
  serviceName: string
  releaseTag: string
  deployedAt: string
  timeSinceDeploymentMinutes: number
  isTemporallyCorrelated: boolean
  preDeploymentMetrics: Record<string, number>
  postDeploymentMetrics: Record<string, number>
  metricDeltas: Record<string, number>
  probableImpactSummary: string
  recommendedInvestigation: string
}

export interface PreventiveRecommendation {
  id: string
  organizationId: string
  serviceId: string
  serviceName: string
  title: string
  description: string
  priority: 'critical' | 'high' | 'medium' | 'low'
  riskLevel: 'critical' | 'high' | 'medium' | 'low'
  category: string
  supportingEvidence: string[]
  expectedBenefit: string
  suggestedAction: string
  status: 'open' | 'acknowledged' | 'dismissed' | 'applied'
  createdAt: string
}

export interface SimilarIncident {
  incidentId: string
  title: string
  serviceName: string
  similarityScore: number
  previousRootCause: string
  previousRecoveryAction: string
  recoveryOutcome: string
  resolutionDurationMinutes?: number
  detectedAt: string
}

export interface IncidentAnalysis {
  incidentId: string
  serviceId: string
  serviceName: string
  summary: string
  probableRootCause: string
  severity: 'critical' | 'high' | 'medium' | 'low'
  riskLevel: 'critical' | 'high' | 'medium' | 'low'
  confidenceScore: number
  affectedComponents: string[]
  confirmedEvidence: string[]
  unverifiedHypotheses: string[]
  potentialBusinessImpact: string
  suggestedInvestigationSteps: string[]
  recommendedRecoveryAction: string
  alternativeRecoveryAction?: string
  preventionRecommendations: string[]
  verificationRequirements: string[]
  similarHistoricalIncidents: SimilarIncident[]
  correlatedIncidentIds: string[]
  deploymentImpact?: DeploymentImpact
  providerSource: 'gemini' | 'heuristic_fallback'
  analyzedAt: string
}

export interface ModelEvaluationMetric {
  modelName: string
  evaluationType: string
  datasetName: string
  isSynthetic: boolean
  sampleCount: number
  precision: number
  recall: number
  f1Score: number
  falsePositiveRate: number
  falseNegativeRate: number
  meanAbsoluteError?: number
  meanLatencyMs: number
  evaluatedAt: string
}

export interface IntelligenceOverview {
  activePredictionsCount: number
  detectedAnomaliesCount: number
  highRiskServicesCount: number
  openRecommendationsCount: number
  predictions: Prediction[]
  anomalies: Anomaly[]
  topRiskServices: ServiceRisk[]
  preventiveRecommendations: PreventiveRecommendation[]
  recentCorrelations: IncidentCorrelationGroup[]
}


// ==============================================================================
// Phase 9: Enterprise Integrations, Notifications, Release Intelligence & Timeline
// ==============================================================================

export type NotificationChannelType = 'email' | 'slack' | 'teams' | 'webhook'
export type NotificationDeliveryStatus = 'pending' | 'processing' | 'delivered' | 'retrying' | 'failed' | 'permanently_failed' | 'disabled'

export interface NotificationChannel {
  id: string
  organizationId: string
  name: string
  channelType: NotificationChannelType
  isEnabled: boolean
  configMasked: Record<string, any>
  rateLimitPerMinute: number
  createdAt: string
  updatedAt: string
}

export interface NotificationSubscription {
  id: string
  organizationId: string
  channelId: string
  eventType: string
  minSeverity: Severity
  isActive: boolean
  createdAt: string
}

export interface NotificationDelivery {
  id: string
  organizationId: string
  channelId: string
  channelName: string
  channelType: string
  incidentId?: string | null
  eventType: string
  idempotencyKey: string
  payload: Record<string, any>
  status: NotificationDeliveryStatus
  retryCount: number
  maxRetries: number
  providerResponseCode?: number | null
  failureReason?: string | null
  deliveredAt?: string | null
  nextRetryAt?: string | null
  createdAt: string
}

export interface WebhookEndpoint {
  id: string
  organizationId: string
  name: string
  targetUrl: string
  isActive: boolean
  events: string[]
  timeoutSeconds: number
  createdAt: string
  updatedAt: string
}

export interface WebhookDeliveryAttempt {
  id: string
  deliveryId: string
  eventType: string
  payload: Record<string, any>
  signatureHeader: string
  responseStatusCode?: number | null
  status: string
  errorMessage?: string | null
  durationMs: number
  createdAt: string
}

export type IncidentCommentType = 'comment' | 'internal_note' | 'status_change' | 'escalation' | 'resolution_summary'

export interface IncidentComment {
  id: string
  incidentId: string
  authorName: string
  authorRole: string
  commentType: IncidentCommentType
  content: string
  createdAt: string
}

export interface IncidentAssignment {
  id: string
  incidentId: string
  assignedToName: string
  assignedByName: string
  assignedAt: string
  isActive: boolean
}

export interface EscalationLevelRule {
  level: number
  timeoutMinutes: number
  channelIds: string[]
  targetRoles: string[]
}

export interface EscalationPolicy {
  id: string
  organizationId: string
  name: string
  severity: Severity
  unacknowledgedTimeoutMinutes: number
  maxEscalationLevel: number
  rules: EscalationLevelRule[]
  quietHoursEnabled: boolean
  quietHoursStartUtc?: string | null
  quietHoursEndUtc?: string | null
  isActive: boolean
  createdAt: string
}

export interface EscalationEvent {
  id: string
  policyId: string
  incidentId: string
  escalationLevel: number
  triggerReason: string
  actionTaken: string
  notifiedChannels: string[]
  escalatedAt: string
}

export interface ReleaseEvaluationMetric {
  metricName: string
  baselineValue: number
  canaryValue: number
  delta: number
  thresholdValue: number
  status: 'pass' | 'warning' | 'breach'
  evaluatedAt: string
}

export interface ReleaseEvaluation {
  id: string
  organizationId: string
  serviceId: string
  serviceName: string
  releaseTag: string
  stage: string
  status: string
  trafficPercentage: number
  observationWindowMinutes: number
  sampleCount: number
  regressionDetected: boolean
  recommendation: 'proceed' | 'pause' | 'rollback_recommended'
  explanation: string
  metrics: ReleaseEvaluationMetric[]
  evaluatedAt: string
  createdAt: string
}

export interface TimelineItem {
  id: string
  category: 'deployment' | 'alert' | 'incident' | 'ai_diagnosis' | 'recovery' | 'notification' | 'escalation'
  title: string
  detail: string
  serviceName?: string | null
  severity?: string | null
  status?: string | null
  timestamp: string
  metadata?: Record<string, any>
}

export interface UnifiedTimeline {
  totalEvents: number
  items: TimelineItem[]
}
