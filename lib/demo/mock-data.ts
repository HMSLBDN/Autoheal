import type { AnalyticsSummary, Incident, InfrastructureAgent, RecoveryAction, Service } from '@/types'

export const demoServices: Service[] = [
  { id: 'svc-api', name: 'checkout-api', environment: 'production', status: 'healthy', availability: 99.98, errorRate: 0.12, latencyMs: 142, lastChecked: '12 sec ago' },
  { id: 'svc-web', name: 'customer-web', environment: 'production', status: 'degraded', availability: 99.72, errorRate: 1.84, latencyMs: 684, lastChecked: '18 sec ago' },
  { id: 'svc-worker', name: 'event-worker', environment: 'production', status: 'healthy', availability: 99.95, errorRate: 0.08, latencyMs: 86, lastChecked: '21 sec ago' },
  { id: 'svc-pg', name: 'primary-postgres', environment: 'production', status: 'healthy', availability: 99.99, errorRate: 0.01, latencyMs: 21, lastChecked: '24 sec ago' },
  { id: 'svc-search', name: 'search-indexer', environment: 'staging', status: 'critical', availability: 96.21, errorRate: 5.4, latencyMs: 1208, lastChecked: '31 sec ago' },
]

export const demoIncidents: Incident[] = [
  {
    id: 'INC-2841', serviceId: 'svc-web', serviceName: 'customer-web', title: 'Elevated API error rate', severity: 'high', status: 'investigating', detectedAt: 'Today, 09:42:18', recoveryStatus: 'Approval required', errorRate: 1.84, threshold: 1.0, probableCause: 'A new upstream payment dependency is returning intermittent 5xx responses.', recommendedAction: 'Shift traffic to the previous stable release and verify checkout health.',
    evidence: [
      { id: 'ev-1', kind: 'metric', title: '5xx rate above threshold', detail: '1.84% over the last 5 minutes (threshold 1.0%)', timestamp: '09:42:18' },
      { id: 'ev-2', kind: 'deployment', title: 'Release deployed', detail: 'release-2026.11.08.3 deployed 8 minutes before alert', timestamp: '09:34:06' },
      { id: 'ev-3', kind: 'log', title: 'Upstream timeout pattern', detail: '18 matching timeout events on payment-provider', timestamp: '09:41:52' },
    ],
    events: [
      { id: 'e1', label: 'Incident detected', detail: 'Error rate crossed the configured 1.0% threshold.', timestamp: '09:42:18', tone: 'warning' },
      { id: 'e2', label: 'Diagnosis completed', detail: 'Three signals correlate with the latest release.', timestamp: '09:43:02', tone: 'neutral' },
      { id: 'e3', label: 'Recovery awaiting approval', detail: 'Rollback recommendation requires an operator.', timestamp: '09:43:14', tone: 'neutral' },
    ],
  },
  { id: 'INC-2838', serviceId: 'svc-search', serviceName: 'search-indexer', title: 'Queue processing delay', severity: 'critical', status: 'open', detectedAt: 'Today, 08:16:40', recoveryStatus: 'Not started', errorRate: 5.4, threshold: 2, probableCause: 'Consumer lag increased after a retry storm.', recommendedAction: 'Scale the consumer group after the queue backlog is inspected.', evidence: [], events: [] },
  { id: 'INC-2835', serviceId: 'svc-api', serviceName: 'checkout-api', title: 'Latency threshold exceeded', severity: 'medium', status: 'resolved', detectedAt: 'Yesterday, 16:28:03', recoveryStatus: 'Verified', errorRate: 0.46, threshold: 0.8, probableCause: 'Database connection pool saturation.', recommendedAction: 'Connection pool limits were adjusted and health checks passed.', evidence: [], events: [] },
  { id: 'INC-2829', serviceId: 'svc-worker', serviceName: 'event-worker', title: 'Worker restart loop', severity: 'low', status: 'resolved', detectedAt: 'Yesterday, 11:05:44', recoveryStatus: 'Verified', errorRate: 0.31, threshold: 1.0, probableCause: 'A transient dependency reset caused worker restarts.', recommendedAction: 'Restart approved worker deployment and verify queue drain.', evidence: [], events: [] },
]

export const demoRecoveries: RecoveryAction[] = [
  { id: 'REC-611', incidentId: 'INC-2841', serviceName: 'customer-web', action: 'Rollback to previous stable release', status: 'pending_approval', approvalRequired: true, requestedBy: 'AutoHeal policy', requestedAt: '09:43:14', verification: 'pending' },
  { id: 'REC-609', incidentId: 'INC-2835', serviceName: 'checkout-api', action: 'Tune database connection pool', status: 'completed', approvalRequired: true, requestedBy: 'Morgan Lee', requestedAt: 'Yesterday, 16:34', durationSeconds: 42, verification: 'passed', result: { verified: true, summary: 'All configured health checks passed.', completedAt: 'Yesterday, 16:35' } },
  { id: 'REC-604', incidentId: 'INC-2829', serviceName: 'event-worker', action: 'Restart worker deployment', status: 'completed', approvalRequired: false, requestedBy: 'AutoHeal policy', requestedAt: 'Yesterday, 11:09', durationSeconds: 18, verification: 'passed', result: { verified: true, summary: 'Queue depth returned to normal.', completedAt: 'Yesterday, 11:10' } },
  { id: 'REC-602', incidentId: 'INC-2838', serviceName: 'search-indexer', action: 'Scale consumer group', status: 'failed', approvalRequired: true, requestedBy: 'Alex Chen', requestedAt: 'Yesterday, 10:24', durationSeconds: 13, verification: 'failed', result: { verified: false, summary: 'Policy precondition was not satisfied.', completedAt: 'Yesterday, 10:25' } },
]

export const demoAnalytics: AnalyticsSummary = {
  detectionLatencySeconds: 42,
  recoveryDurationMinutes: 6.4,
  recoverySuccessRate: 94.2,
  falsePositiveRate: 2.1,
  availability: 99.94,
  incidentCount: 18,
  history: [
    { date: 'Mon', incidents: 8, recoveries: 6, availability: 99.82 },
    { date: 'Tue', incidents: 5, recoveries: 4, availability: 99.91 },
    { date: 'Wed', incidents: 7, recoveries: 6, availability: 99.88 },
    { date: 'Thu', incidents: 4, recoveries: 4, availability: 99.96 },
    { date: 'Fri', incidents: 6, recoveries: 5, availability: 99.9 },
    { date: 'Sat', incidents: 3, recoveries: 3, availability: 99.97 },
    { date: 'Sun', incidents: 4, recoveries: 4, availability: 99.94 },
  ],
}

export const demoAgents: InfrastructureAgent[] = [
  {
    id: 'agent-prod-edge-01',
    organizationId: 'org-demo-1',
    name: 'prod-edge-cluster-01',
    hostname: 'edge-node-01.internal.autoheal',
    ipAddress: '10.240.0.12',
    environment: 'production',
    status: 'online',
    version: '1.2.0',
    capabilities: ['docker_restart', 'container_logs', 'health_check'],
    publicKeyFingerprint: 'SHA256:d8a7c29e1f5b4a03c8e9f1a2b3c4d5e6',
    lastHeartbeat: '14 sec ago',
    createdAt: '2026-11-01T08:00:00Z',
  },
  {
    id: 'agent-prod-k8s-01',
    organizationId: 'org-demo-1',
    name: 'prod-k8s-operator',
    hostname: 'k8s-control-01.internal.autoheal',
    ipAddress: '10.240.1.45',
    environment: 'production',
    status: 'online',
    version: '1.2.0',
    capabilities: ['k8s_rollout_restart', 'pod_status', 'workload_events', 'health_check'],
    publicKeyFingerprint: 'SHA256:9f8e7d6c5b4a3a2b1c0d9e8f7a6b5c4d',
    lastHeartbeat: '28 sec ago',
    createdAt: '2026-11-05T12:00:00Z',
  },
  {
    id: 'agent-staging-dock-01',
    organizationId: 'org-demo-1',
    name: 'staging-worker-host',
    hostname: 'stg-worker-01.internal.autoheal',
    ipAddress: '10.241.0.8',
    environment: 'staging',
    status: 'online',
    version: '1.1.9',
    capabilities: ['docker_restart', 'container_logs'],
    publicKeyFingerprint: 'SHA256:1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d',
    lastHeartbeat: '45 sec ago',
    createdAt: '2026-11-10T09:30:00Z',
  },
]

