'use client'

import { useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import Link from 'next/link'
import useSWR from 'swr'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Bell,
  CheckCircle2,
  CircleAlert,
  Clock3,
  GitBranch,
  History,
  Lock,
  MessageSquare,
  RefreshCw,
  Send,
  Server,
  ShieldCheck,
  UserCheck,
  Zap,
} from 'lucide-react'
import type {
  EscalationEvent,
  EscalationPolicy,
  Incident,
  IncidentAssignment,
  IncidentComment,
  NotificationChannel,
  NotificationDelivery,
  ReleaseEvaluation,
  TimelineItem,
  UnifiedTimeline,
  WebhookEndpoint,
} from '@/types'
import { collaborationApi, escalationsApi, notificationsApi, releasesApi, timelineApi, webhooksApi } from '@/lib/api/resources'
import {
  demoEscalationPolicies,
  demoIncidentComments,
  demoNotificationChannels,
  demoNotificationDeliveries,
  demoReleaseEvaluations,
  demoTimeline,
} from '@/lib/demo/mock-data'

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty-state" role="status">
      <span className="empty-state-icon"><Activity size={15} /></span>
      <strong>{title}</strong>
      <p>{detail}</p>
    </div>
  )
}

// ==============================================================================
// 1. Enterprise Notifications & Webhooks View
// ==============================================================================

export function NotificationsView({ demoMode }: { demoMode: boolean }) {
  const [activeTab, setActiveTab] = useState<'channels' | 'escalations' | 'deliveries'>('channels')
  const [testResult, setTestResult] = useState<{ id: string; status: string; detail: string } | null>(null)
  const [busyId, setBusyId] = useState('')

  const channelsResource = useSWR<NotificationChannel[]>(
    demoMode ? 'demo-channels' : 'notification-channels',
    () => demoMode ? Promise.resolve(demoNotificationChannels) : notificationsApi.listChannels(),
    { fallbackData: demoMode ? demoNotificationChannels : undefined, revalidateOnFocus: false }
  )

  const policiesResource = useSWR<EscalationPolicy[]>(
    demoMode ? 'demo-policies' : 'escalation-policies',
    () => demoMode ? Promise.resolve(demoEscalationPolicies) : escalationsApi.listPolicies(),
    { fallbackData: demoMode ? demoEscalationPolicies : undefined, revalidateOnFocus: false }
  )

  const deliveriesResource = useSWR<NotificationDelivery[]>(
    demoMode ? 'demo-deliveries' : 'notification-deliveries',
    () => demoMode ? Promise.resolve(demoNotificationDeliveries) : notificationsApi.listDeliveries(),
    { fallbackData: demoMode ? demoNotificationDeliveries : undefined, revalidateOnFocus: false }
  )

  const channels = channelsResource.data ?? []
  const policies = policiesResource.data ?? []
  const deliveries = deliveriesResource.data ?? []

  async function handleSendTest(channelId: string) {
    setBusyId(channelId)
    setTestResult(null)
    try {
      if (demoMode) {
        setTestResult({ id: channelId, status: 'delivered', detail: 'Test alert dispatched successfully (Demo Mode simulated).' })
      } else {
        const res = await notificationsApi.testChannel(channelId, 'Manual test dispatch from AutoHeal Notifications Center.')
        setTestResult({ id: channelId, status: res.status, detail: res.detail })
        deliveriesResource.mutate()
      }
    } catch (err: any) {
      setTestResult({ id: channelId, status: 'failed', detail: err.message || 'Test dispatch failed.' })
    } finally {
      setBusyId('')
    }
  }

  async function handleRetryDelivery(deliveryId: string) {
    setBusyId(deliveryId)
    try {
      if (!demoMode) {
        await notificationsApi.retryDelivery(deliveryId)
        deliveriesResource.mutate()
      }
    } catch {
      // Ignored
    } finally {
      setBusyId('')
    }
  }

  return (
    <>
      <div className="dashboard-heading">
        <div>
          <h1>Notification Center & Integrations</h1>
          <p>Multi-channel adapters (Slack, Teams, Email, Signed Webhooks), escalation policies, and delivery logs.</p>
        </div>
        <div className="dashboard-toolbar">
          <span className={`demo-label ${demoMode ? '' : 'live'}`}>
            <span className="status-dot" />
            {demoMode ? 'DEMO DATA' : 'LIVE API'}
          </span>
          <div style={{ display: 'flex', gap: '6px' }}>
            <button
              className={`dash-button ${activeTab === 'channels' ? 'primary' : ''}`}
              onClick={() => setActiveTab('channels')}
            >
              <Bell size={12} />Channels ({channels.length})
            </button>
            <button
              className={`dash-button ${activeTab === 'escalations' ? 'primary' : ''}`}
              onClick={() => setActiveTab('escalations')}
            >
              <ShieldCheck size={12} />Escalation Policies ({policies.length})
            </button>
            <button
              className={`dash-button ${activeTab === 'deliveries' ? 'primary' : ''}`}
              onClick={() => setActiveTab('deliveries')}
            >
              <History size={12} />Delivery Audit ({deliveries.length})
            </button>
          </div>
        </div>
      </div>

      {testResult && (
        <div className={`notice-strip ${testResult.status === 'delivered' ? 'live' : ''}`} style={{ marginBottom: 12 }}>
          <strong>{testResult.status === 'delivered' ? 'Success:' : 'Notice:'}</strong> {testResult.detail}
        </div>
      )}

      {activeTab === 'channels' && (
        <section className="dash-card panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Configured Notification Channels</h2>
              <p className="panel-subtitle">Channels remain disabled by default until explicitly verified and activated. Tokens are masked server-side.</p>
            </div>
          </div>
          {channels.length ? (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Channel Name</th>
                    <th>Type</th>
                    <th>Status</th>
                    <th>Masked Configuration</th>
                    <th>Rate Limit</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map((c) => (
                    <tr key={c.id}>
                      <td><strong>{c.name}</strong></td>
                      <td>
                        <span className="table-badge" style={{ textTransform: 'uppercase' }}>
                          {c.channelType}
                        </span>
                      </td>
                      <td>
                        <span className={`status-chip ${c.isEnabled ? 'completed' : 'degraded'}`}>
                          {c.isEnabled ? 'Active' : 'Disabled'}
                        </span>
                      </td>
                      <td>
                        <code style={{ fontSize: '11px', color: '#94a3b8' }}>
                          {JSON.stringify(c.configMasked)}
                        </code>
                      </td>
                      <td>{c.rateLimitPerMinute} / min</td>
                      <td>
                        <button
                          className="dash-button"
                          disabled={busyId === c.id}
                          onClick={() => handleSendTest(c.id)}
                        >
                          <Send size={11} />
                          {busyId === c.id ? 'Sending…' : 'Test Ping'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No notification channels configured" detail="Configure notification adapters to route incident updates to your team." />
          )}
        </section>
      )}

      {activeTab === 'escalations' && (
        <section className="dash-card panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Escalation Policies</h2>
              <p className="panel-subtitle">Automatic unacknowledged timeout escalations with quiet hours suppression.</p>
            </div>
          </div>
          {policies.length ? (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Policy Name</th>
                    <th>Severity Trigger</th>
                    <th>Timeout (Minutes)</th>
                    <th>Levels</th>
                    <th>Quiet Hours (UTC)</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {policies.map((p) => (
                    <tr key={p.id}>
                      <td><strong>{p.name}</strong></td>
                      <td>
                        <span className={`status-chip ${p.severity === 'critical' ? 'critical' : 'degraded'}`}>
                          {p.severity.toUpperCase()}
                        </span>
                      </td>
                      <td>{p.unacknowledgedTimeoutMinutes}m unacknowledged</td>
                      <td>Max Level {p.maxEscalationLevel} ({p.rules.length} stages)</td>
                      <td>
                        {p.quietHoursEnabled
                          ? `${p.quietHoursStartUtc || '22:00'} - ${p.quietHoursEndUtc || '06:00'}`
                          : 'Disabled'}
                      </td>
                      <td>
                        <span className={`status-chip ${p.isActive ? 'completed' : 'degraded'}`}>
                          {p.isActive ? 'Active' : 'Disabled'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No escalation policies configured" detail="Escalation policies ensure critical unacknowledged incidents are automatically escalated." />
          )}
        </section>
      )}

      {activeTab === 'deliveries' && (
        <section className="dash-card panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Delivery Audit & History</h2>
              <p className="panel-subtitle">Idempotent dispatches with exponential backoff retry logs.</p>
            </div>
          </div>
          {deliveries.length ? (
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Target Channel</th>
                    <th>Event Type</th>
                    <th>Delivery Status</th>
                    <th>HTTP Code</th>
                    <th>Retries</th>
                    <th>Dispatched At</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {deliveries.map((d) => (
                    <tr key={d.id}>
                      <td><strong>{d.channelName}</strong></td>
                      <td><span className="table-badge">{d.eventType}</span></td>
                      <td>
                        <span className={`status-chip ${d.status === 'delivered' ? 'completed' : d.status === 'failed' || d.status === 'permanently_failed' ? 'critical' : 'degraded'}`}>
                          {d.status}
                        </span>
                      </td>
                      <td>{d.providerResponseCode ?? '—'}</td>
                      <td>{d.retryCount} / {d.maxRetries}</td>
                      <td><small className="table-subtext">{d.createdAt}</small></td>
                      <td>
                        {d.status === 'failed' || d.status === 'retrying' ? (
                          <button
                            className="dash-button"
                            disabled={busyId === d.id}
                            onClick={() => handleRetryDelivery(d.id)}
                          >
                            <RefreshCw size={11} /> Retry
                          </button>
                        ) : (
                          <span style={{ color: '#64748b', fontSize: '11px' }}>Delivered</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState title="No delivery records found" detail="Outbound notification dispatches will be recorded here." />
          )}
        </section>
      )}
    </>
  )
}

// ==============================================================================
// 2. Canary Release & Rollback Intelligence View
// ==============================================================================

export function CanaryReleasesView({ demoMode }: { demoMode: boolean }) {
  const evaluationsResource = useSWR<ReleaseEvaluation[]>(
    demoMode ? 'demo-release-evals' : 'release-evaluations',
    () => demoMode ? Promise.resolve(demoReleaseEvaluations) : releasesApi.listEvaluations(),
    { fallbackData: demoMode ? demoReleaseEvaluations : undefined, revalidateOnFocus: false }
  )

  const evaluations = evaluationsResource.data ?? []

  return (
    <>
      <div className="dashboard-heading">
        <div>
          <h1>Release Intelligence & Canary Evaluation</h1>
          <p>Progressive canary telemetry analysis, baseline delta tracking, and simulated rollback advisory.</p>
        </div>
        <div className="dashboard-toolbar">
          <span className={`demo-label ${demoMode ? '' : 'live'}`}>
            <span className="status-dot" />
            {demoMode ? 'DEMO DATA' : 'LIVE API'}
          </span>
          <span className="demo-label" style={{ background: 'rgba(53, 214, 197, 0.1)', color: '#35D6C5', border: '1px solid rgba(53, 214, 197, 0.3)' }}>
            SIMULATED ADVISORY ONLY
          </span>
        </div>
      </div>

      <div className="notice-strip" style={{ marginBottom: 14 }}>
        <strong>Safety Guarantee:</strong> All canary rollback recommendations are strictly advisory and simulated. Real production infrastructure is never modified or rolled back automatically.
      </div>

      {evaluations.map((ev) => (
        <section className="dash-card panel" key={ev.id} style={{ marginBottom: 16 }}>
          <div className="panel-header">
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <h2 className="panel-title">{ev.serviceName}: {ev.releaseTag}</h2>
                <span className={`status-chip ${ev.status === 'passed' ? 'completed' : 'critical'}`}>
                  {ev.stage.replace('_', ' ').toUpperCase()}
                </span>
                <span className="table-badge">Traffic: {ev.trafficPercentage}%</span>
              </div>
              <p className="panel-subtitle">Observation window: {ev.observationWindowMinutes}m · Samples collected: {ev.sampleCount}</p>
            </div>
            <div>
              <span className={`status-chip ${ev.recommendation === 'proceed' ? 'completed' : 'critical'}`}>
                Recommendation: {ev.recommendation.replace('_', ' ').toUpperCase()}
              </span>
            </div>
          </div>

          <div style={{ padding: '10px 16px', background: 'rgba(15, 23, 42, 0.6)', borderBottom: '1px solid rgba(148, 163, 184, 0.1)' }}>
            <p style={{ margin: 0, fontSize: '12px', color: '#e2e8f0', lineHeight: 1.5 }}>
              <strong>Advisory Analysis:</strong> {ev.explanation}
            </p>
          </div>

          <div className="table-responsive">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Metric Name</th>
                  <th>Baseline Value</th>
                  <th>Canary Value</th>
                  <th>Delta</th>
                  <th>Threshold</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {ev.metrics.map((m, idx) => (
                  <tr key={idx}>
                    <td><strong>{m.metricName}</strong></td>
                    <td>{m.baselineValue}</td>
                    <td><strong>{m.canaryValue}</strong></td>
                    <td>
                      <span style={{ color: m.status === 'breach' ? '#f87171' : '#35D6C5' }}>
                        {m.delta > 0 ? `+${m.delta}` : m.delta}
                      </span>
                    </td>
                    <td>{m.thresholdValue}</td>
                    <td>
                      <span className={`status-chip ${m.status === 'pass' ? 'completed' : m.status === 'warning' ? 'degraded' : 'critical'}`}>
                        {m.status.toUpperCase()}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      {!evaluations.length && (
        <EmptyState title="No release evaluations found" detail="Evaluate canary deployments via POST /api/v1/releases/evaluate-canary to analyze rollout metrics." />
      )}
    </>
  )
}

// ==============================================================================
// 3. Unified Operations Timeline View
// ==============================================================================

export function OperationsTimelineView({ demoMode }: { demoMode: boolean }) {
  const timelineResource = useSWR<UnifiedTimeline>(
    demoMode ? 'demo-timeline' : 'unified-timeline',
    () => demoMode ? Promise.resolve(demoTimeline) : timelineApi.getTimeline(),
    { fallbackData: demoMode ? demoTimeline : undefined, revalidateOnFocus: false }
  )

  const items = timelineResource.data?.items ?? []

  function getCategoryColor(cat: string) {
    switch (cat) {
      case 'deployment': return '#38bdf8'
      case 'alert': return '#f59e0b'
      case 'incident': return '#ef4444'
      case 'ai_diagnosis': return '#7C6CFF'
      case 'recovery': return '#35D6C5'
      case 'notification': return '#10b981'
      case 'escalation': return '#ec4899'
      default: return '#94a3b8'
    }
  }

  return (
    <>
      <div className="dashboard-heading">
        <div>
          <h1>Unified Operations Timeline</h1>
          <p>Chronological correlation of deployments, telemetry alerts, incidents, diagnoses, recoveries, and escalations.</p>
        </div>
        <div className="dashboard-toolbar">
          <span className={`demo-label ${demoMode ? '' : 'live'}`}>
            <span className="status-dot" />
            {demoMode ? 'DEMO DATA' : 'LIVE API'}
          </span>
          <span className="demo-label">{items.length} chronological events</span>
        </div>
      </div>

      <section className="dash-card panel">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">End-to-End Operational Lifecycle</h2>
            <p className="panel-subtitle">All events merged and ordered by timestamp.</p>
          </div>
        </div>

        <div className="activity-list" style={{ padding: '8px 16px' }}>
          {items.map((it) => (
            <div className="activity-item" key={it.id}>
              <span
                className="activity-bullet"
                style={{
                  background: getCategoryColor(it.category),
                  color: '#080B12',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Clock3 size={11} />
              </span>
              <div className="activity-text">
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                  <strong>{it.title}</strong>
                  <span
                    className="table-badge"
                    style={{
                      background: 'rgba(255,255,255,0.05)',
                      color: getCategoryColor(it.category),
                      borderColor: 'rgba(255,255,255,0.1)',
                      fontSize: '9px',
                      textTransform: 'uppercase',
                    }}
                  >
                    {it.category.replace('_', ' ')}
                  </span>
                  {it.serviceName && (
                    <span className="table-subtext" style={{ fontSize: '10px' }}>
                      ({it.serviceName})
                    </span>
                  )}
                </div>
                <div style={{ fontSize: '11px', color: '#cbd5e1' }}>{it.detail}</div>
                <small className="table-subtext">{it.timestamp}</small>
              </div>
            </div>
          ))}

          {!items.length && (
            <EmptyState title="No timeline events recorded" detail="Operational events will appear chronologically as services operate." />
          )}
        </div>
      </section>
    </>
  )
}

// ==============================================================================
// 4. Incident Collaboration Panel (Comments, Notes, Assignment, Acknowledge)
// ==============================================================================

export function IncidentCollaborationPanel({
  incident,
  demoMode,
  onIncidentUpdated,
}: {
  incident: Incident
  demoMode: boolean
  onIncidentUpdated?: () => void
}) {
  const [commentText, setCommentText] = useState('')
  const [commentType, setCommentType] = useState<'comment' | 'internal_note'>('comment')
  const [assigneeName, setAssigneeName] = useState('')
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [acknowledgedLocally, setAcknowledgedLocally] = useState(false)

  const commentsResource = useSWR<IncidentComment[]>(
    demoMode ? `demo-comments-${incident.id}` : `incident-comments-${incident.id}`,
    () => demoMode ? Promise.resolve(demoIncidentComments) : collaborationApi.listComments(incident.id),
    { fallbackData: demoMode ? demoIncidentComments : undefined, revalidateOnFocus: false }
  )

  const assignmentResource = useSWR<IncidentAssignment | null>(
    demoMode ? `demo-assignment-${incident.id}` : `incident-assignment-${incident.id}`,
    () => demoMode ? Promise.resolve({ id: 'a1', incidentId: incident.id, assignedToName: 'Alex Chen (SRE)', assignedByName: 'AutoHeal System', assignedAt: 'Today, 09:44', isActive: true }) : collaborationApi.getAssignment(incident.id),
    { revalidateOnFocus: false }
  )

  const comments = commentsResource.data ?? []
  const assignment = assignmentResource.data

  async function handleAddComment() {
    if (!commentText.trim()) return
    setIsSubmitting(true)
    try {
      if (demoMode) {
        commentsResource.mutate([
          ...comments,
          {
            id: `comm-${Date.now()}`,
            incidentId: incident.id,
            authorName: 'Alex Chen',
            authorRole: 'operator',
            commentType,
            content: commentText.trim(),
            createdAt: 'Just now',
          },
        ], false)
        setCommentText('')
      } else {
        await collaborationApi.createComment(incident.id, commentText.trim(), commentType)
        setCommentText('')
        commentsResource.mutate()
      }
    } catch {
      // Ignored
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleAcknowledge() {
    setIsSubmitting(true)
    try {
      setAcknowledgedLocally(true)
      if (!demoMode) {
        await collaborationApi.acknowledgeIncident(incident.id, 'Acknowledged by on-call operator in incident details.')
        commentsResource.mutate()
      }
      onIncidentUpdated?.()
    } catch {
      // Ignored
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleAssign() {
    if (!assigneeName.trim()) return
    setIsSubmitting(true)
    try {
      if (demoMode) {
        assignmentResource.mutate({
          id: `asg-${Date.now()}`,
          incidentId: incident.id,
          assignedToName: assigneeName.trim(),
          assignedByName: 'You',
          assignedAt: 'Just now',
          isActive: true,
        }, false)
        setAssigneeName('')
      } else {
        await collaborationApi.assignIncident(incident.id, assigneeName.trim())
        setAssigneeName('')
        assignmentResource.mutate()
        commentsResource.mutate()
      }
    } catch {
      // Ignored
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="dash-card panel" style={{ marginTop: 14 }}>
      <div className="panel-header">
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <h2 className="panel-title">Incident Collaboration & Ownership</h2>
            {assignment && (
              <span className="demo-label" style={{ background: 'rgba(53, 214, 197, 0.1)', color: '#35D6C5' }}>
                Owner: {assignment.assignedToName}
              </span>
            )}
          </div>
          <p className="panel-subtitle">Post updates, record internal triage notes, acknowledge alerts, and assign ownership.</p>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          {incident.status === 'open' && !acknowledgedLocally && (
            <button
              className="dash-button primary"
              disabled={isSubmitting}
              onClick={handleAcknowledge}
            >
              <UserCheck size={12} /> Acknowledge Alert
            </button>
          )}
        </div>
      </div>

      <div style={{ padding: '12px 16px', borderBottom: '1px solid rgba(148, 163, 184, 0.1)' }}>
        <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
          <input
            type="text"
            className="small-select"
            placeholder="Assign owner (e.g. Alex Chen)..."
            value={assigneeName}
            onChange={(e) => setAssigneeName(e.target.value)}
            style={{ width: '220px', padding: '6px 10px', fontSize: '11px' }}
          />
          <button
            className="dash-button"
            disabled={!assigneeName.trim() || isSubmitting}
            onClick={handleAssign}
          >
            Assign Owner
          </button>
        </div>

        <div style={{ display: 'flex', gap: '8px', marginTop: '10px' }}>
          <textarea
            className="small-select"
            rows={2}
            placeholder="Add a comment or internal triage note..."
            value={commentText}
            onChange={(e) => setCommentText(e.target.value)}
            style={{ flex: 1, padding: '8px 10px', fontSize: '12px', resize: 'vertical' }}
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <select
              className="small-select"
              value={commentType}
              onChange={(e) => setCommentType(e.target.value as any)}
              style={{ fontSize: '10px' }}
            >
              <option value="comment">Public Comment</option>
              <option value="internal_note">Internal Note</option>
            </select>
            <button
              className="dash-button primary"
              disabled={!commentText.trim() || isSubmitting}
              onClick={handleAddComment}
            >
              <Send size={11} /> Post
            </button>
          </div>
        </div>
      </div>

      <div className="activity-list" style={{ padding: '12px 16px' }}>
        {comments.map((c) => (
          <div className="activity-item" key={c.id}>
            <span className={`activity-bullet ${c.commentType === 'internal_note' ? 'warning' : 'neutral'}`}>
              <MessageSquare size={11} />
            </span>
            <div className="activity-text">
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <strong>{c.authorName}</strong>
                <span className="table-badge" style={{ fontSize: '9px' }}>{c.authorRole}</span>
                {c.commentType === 'internal_note' && (
                  <span className="table-badge" style={{ color: '#FBBF24', borderColor: 'rgba(251, 191, 36, 0.3)', fontSize: '9px' }}>
                    INTERNAL NOTE
                  </span>
                )}
                {c.commentType === 'escalation' && (
                  <span className="table-badge" style={{ color: '#F87171', borderColor: 'rgba(248, 113, 113, 0.3)', fontSize: '9px' }}>
                    ESCALATED
                  </span>
                )}
              </div>
              <div style={{ fontSize: '11px', color: '#e2e8f0', marginTop: '2px' }}>{c.content}</div>
              <small className="table-subtext">{c.createdAt}</small>
            </div>
          </div>
        ))}

        {!comments.length && (
          <EmptyState title="No communication recorded" detail="Post a comment or note to begin the incident collaboration timeline." />
        )}
      </div>
    </div>
  )
}
