export type ServiceStatus = 'healthy' | 'degraded' | 'critical'
export type Severity = 'critical' | 'high' | 'medium' | 'low'
export type IncidentStatus =
  | 'open'
  | 'investigating'
  | 'recovering'
  | 'resolved'
  | 'new'
  | 'acknowledged'
  | 'investigation'
  | 'diagnosis'
  | 'approval_pending'
  | 'recovery_in_progress'
  | 'recovery_verification'
  | 'failed_recovery'
  | 'escalated'
  | 'reopened'
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

// ==============================================================================
// Phase 10: Enterprise Security, Observability, and mTLS Types
// ==============================================================================

export interface IdentityProvider {
  id: string
  organization_id: string
  name: string
  idp_type: string
  issuer_url: string
  client_id: string
  client_secret_masked: string
  metadata_url?: string | null
  jwks_url?: string | null
  authorization_endpoint?: string | null
  token_endpoint?: string | null
  userinfo_endpoint?: string | null
  role_mapping_json: Record<string, string[]>
  allowed_domains: string[]
  is_active: boolean
  is_enforced: boolean
  created_at: string
  updated_at: string
}

export interface UserSession {
  id: string
  user_id: string
  organization_id: string
  family_id: string
  ip_address?: string | null
  user_agent?: string | null
  device_name?: string | null
  is_active: boolean
  expires_at: string
  created_at: string
  revoked_at?: string | null
  revocation_reason?: string | null
  is_current?: boolean
}

export interface SecurityAuditEvent {
  id: string
  organization_id: string
  user_id?: string | null
  event_type: string
  severity: 'INFO' | 'WARNING' | 'CRITICAL'
  ip_address?: string | null
  user_agent?: string | null
  details_json: Record<string, any>
  created_at: string
}

export interface SecurityAuditSummary {
  total_events: number
  critical_events: number
  warning_events: number
  recent_suspicious_activities: SecurityAuditEvent[]
}

export interface AgentCertificate {
  id: string
  organization_id: string
  agent_id: string
  serial_number: string
  fingerprint_sha256: string
  subject_dn: string
  issuer_dn: string
  valid_from: string
  valid_to: string
  is_revoked: boolean
  revoked_at?: string | null
  revocation_reason?: string | null
  cert_pem: string
  created_at: string
}

export interface ObservabilityMetrics {
  total_requests: number
  error_requests: number
  error_rate_pct: number
  avg_latency_ms: number
  total_mtls_handshakes: number
  successful_mtls_handshakes: number
  db_pool: {
    pool_size: number
    checked_out: number
    overflow: number
  }
  total_recoveries: number
  total_security_events: number
}

export interface TraceSpan {
  trace_id: string
  span_id: string
  name: string
  service: string
  duration_ms: number
  status: string
  attributes: Record<string, any>
  timestamp: string
}

export interface OnboardingStep {
  id: string
  title: string
  description: string
  completed: boolean
  action_url: string
  details?: string | null
}

export interface OnboardingChecklist {
  organization_id: string
  organization_name: string
  plan: string
  completion_percentage: number
  is_ready_for_pilot: boolean
  steps: OnboardingStep[]
  stats: Record<string, any>
}

export interface TeamInvitation {
  id: string
  email: string
  role: string
  organization_id: string
  invited_by_email?: string | null
  invitation_token?: string | null
  invite_url?: string | null
  expires_at: string
  is_accepted: boolean
  created_at: string
}

export interface SLOMetricItem {
  name: string
  metric_key: string
  current_value: number
  target_value: number
  unit: string
  status: 'compliant' | 'at_risk' | 'breached'
  source: 'MEASURED' | 'CALCULATED' | 'SYNTHETIC_DEMO'
  description: string
  sample_count: number
}

export interface SLOSummary {
  organization_id: string
  period: string
  overall_compliance_percent: number
  overall_status: 'compliant' | 'at_risk' | 'breached'
  metrics: SLOMetricItem[]
  calculated_at: string
}

export interface IncidentTransitionAudit {
  id: string
  incident_id: string
  actor_email: string
  actor_role: string
  previous_state: string
  new_state: string
  reason: string
  evidence_id?: string | null
  sign_off: boolean
  created_at: string
}

// Phase 14 Experiment & Benchmark Interfaces
export type ScenarioType =
  | 'healthy_baseline'
  | 'service_unavailable'
  | 'high_error_rate'
  | 'resource_exhaustion'
  | 'repeated_alerts'
  | 'verification_failure'
  | 'recovery_verification_failure'
  | 'unauthorized_recovery'
  | 'unapproved_recovery'

export type ExperimentStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'
export type EvidenceClassification = 'MEASURED' | 'CALCULATED' | 'SYNTHETIC' | 'SIMULATED'

export interface MetricDistribution {
  min: number | null
  max: number | null
  mean: number | null
  median: number | null
  std_dev: number | null
  p95: number | null
  sample_count: number
  small_sample_size: boolean
  unit: string
  classification: EvidenceClassification
}

export interface ExperimentRun {
  id: string
  experiment_id: string
  run_number: number
  status: ExperimentStatus
  recovery_enabled: boolean
  seed: number
  fault_injected_at?: string | null
  detected_at?: string | null
  recovery_started_at?: string | null
  recovery_completed_at?: string | null
  health_restored_at?: string | null
  detection_latency_ms?: number | null
  recovery_duration_ms?: number | null
  total_outage_duration_ms?: number | null
  recovery_attempted: boolean
  recovery_verified: boolean
  recovery_success: boolean
  is_false_positive: boolean
  safety_compliant: boolean
  escalated: boolean
  incident_id?: string | null
  recovery_action_id?: string | null
  evidence_classification: EvidenceClassification
  telemetry_samples: Array<Record<string, any>>
  execution_log: Array<Record<string, any>>
  error_message?: string | null
  started_at?: string | null
  completed_at?: string | null
  created_at: string
}

export interface Experiment {
  id: string
  organization_id: string
  created_by_user_id?: string | null
  name: string
  description: string
  scenario_type: ScenarioType
  execution_mode: string
  recovery_enabled: boolean
  target_service_id: string
  number_of_runs: number
  random_seed: number
  configuration: Record<string, any>
  test_conditions: Record<string, any>
  status: ExperimentStatus
  started_at?: string | null
  completed_at?: string | null
  results_summary: Record<string, any>
  runs_count: number
  runs?: ExperimentRun[]
  created_at: string
  updated_at: string
}

export interface ExperimentAnalytics {
  experiment_id: string
  scenario_type: string
  recovery_enabled: boolean
  total_runs: number
  completed_runs: number
  detection_latency: MetricDistribution
  recovery_duration: MetricDistribution
  total_outage_duration: MetricDistribution
  recovery_success_rate: number
  false_positive_rate: number
  safety_compliance_rate: number
  escalation_rate: number
  evidence_classification: EvidenceClassification
  sample_size_warning?: string | null
}

export interface ExperimentComparison {
  scenario_type: string
  random_seed: number
  enabled_experiment?: ExperimentAnalytics | null
  disabled_experiment?: ExperimentAnalytics | null
  outage_reduction_ms?: number | null
  outage_reduction_percentage?: number | null
  mttr_improvement_percentage?: number | null
  is_statistically_significant: boolean
  confidence_note: string
  evidence_classification: EvidenceClassification
}


