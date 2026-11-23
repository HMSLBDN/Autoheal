'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import useSWR from 'swr'
import type { LucideIcon } from 'lucide-react'
import { Activity, ArrowDownRight, CheckCircle2, CircleAlert, Clock3, Download, FileText, RefreshCw, Server, ShieldAlert, ShieldCheck } from 'lucide-react'
import type { AnalyticsSummary, Anomaly, Incident, IncidentCorrelationGroup, InfrastructureAgent, IntelligenceOverview, ModelEvaluationMetric, Prediction, PreventiveRecommendation, RecoveryAction, Service, ServiceRisk } from '@/types'
import { isApiConfigured, isDemoMode } from '@/lib/api/client'
import { agentsApi, analyticsApi, healthApi, incidentsApi, intelligenceApi, recoveriesApi, servicesApi } from '@/lib/api/resources'
import { useRealtimeEvents } from '@/lib/api/events'
import { demoAgents, demoAnalytics, demoAnomalies, demoCorrelations, demoEvaluations, demoIncidents, demoIntelligenceOverview, demoPredictions, demoRecommendations, demoRecoveries, demoRiskScores, demoServices } from '@/lib/demo/mock-data'
import { useDashboardControls } from '@/components/dashboard/dashboard-shell'
import { AgentsView, AnalyticsView, EmptyState, IncidentTable, IncidentDetailView, IntelligenceView, MonitoringView, OverviewView, RecoveryTable, ReportsView, SectionErrorState, ServiceDetailView, ServiceTable, SettingsView } from '@/components/dashboard/data-views'
import { CanaryReleasesView, IncidentCollaborationPanel, NotificationsView, OperationsTimelineView } from '@/components/dashboard/enterprise-views'
import { ExperimentsView } from '@/components/dashboard/experiment-views'
import { ObservabilityCenterView, SecurityCenterView } from '@/components/dashboard/security-views'
import { ChartSkeleton, ListSkeleton, MetricCardSkeleton, TableSkeleton } from '@/components/ui/skeleton'

type DialogState = {
  title: string
  description: string
  confirmLabel?: string
  confirmTone?: 'primary' | 'danger'
  inputPrompt?: {
    label: string
    placeholder?: string
    defaultValue?: string
    required?: boolean
    maxLength?: number
  }
  onConfirm?: (inputValue?: string) => Promise<void> | void
}

function ConfirmDialog({ dialog, onClose, busy }: { dialog: DialogState; onClose: () => void; busy: boolean }) {
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef(onClose)
  const maxLength = dialog.inputPrompt?.maxLength ?? 500
  const [inputValue, setInputValue] = useState(dialog.inputPrompt?.defaultValue ?? '')
  const [inputError, setInputError] = useState<string | null>(null)

  useEffect(() => { closeRef.current = onClose }, [onClose])
  useEffect(() => {
    const panel = panelRef.current
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const textInput = panel ? panel.querySelector<HTMLTextAreaElement | HTMLInputElement>('textarea, input') : null
    const focusable = panel ? Array.from(panel.querySelectorAll<HTMLElement>('button:not(:disabled), textarea, input')) : []
    ;(textInput ?? focusable[0] ?? panel)?.focus()
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') closeRef.current()
      if (event.key === 'Tab' && focusable.length > 0) {
        const first = focusable[0]
        const last = focusable[focusable.length - 1]
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      if (previousFocus?.isConnected) previousFocus.focus()
    }
  }, [])

  const handleInputChange = (event: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = event.target.value
    setInputValue(value)
    if (value.length > maxLength) {
      setInputError(`Rejection reason cannot exceed ${maxLength} characters.`)
    } else if (dialog.inputPrompt?.required && !value.trim()) {
      setInputError('A reason is required.')
    } else {
      setInputError(null)
    }
  }

  const isDanger = dialog.confirmTone === 'danger'
  const isOverLimit = inputValue.length > maxLength
  const cannotConfirm = busy || isOverLimit || (Boolean(dialog.inputPrompt?.required) && !inputValue.trim())

  const handleConfirm = async () => {
    if (cannotConfirm) return
    const action = dialog.onConfirm
    onClose()
    await action?.(inputValue)
  }

  return (
    <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <section
        ref={panelRef}
        tabIndex={-1}
        className="dialog-card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-description"
      >
        <div className={`dialog-icon ${isDanger ? 'danger' : ''}`}>
          {isDanger ? <ShieldAlert size={17} /> : <ShieldCheck size={17} />}
        </div>
        <h2 id="dialog-title">{dialog.title}</h2>
        <p id="dialog-description">{dialog.description}</p>

        {dialog.inputPrompt && (
          <div className="dialog-input-group">
            <div className="dialog-input-label-row">
              <label htmlFor="dialog-rejection-input" className="dialog-input-label">
                {dialog.inputPrompt.label}
              </label>
              <span className={`dialog-char-counter ${isOverLimit ? 'over-limit' : ''}`}>
                {inputValue.length}/{maxLength}
              </span>
            </div>
            <textarea
              id="dialog-rejection-input"
              className={`dialog-textarea ${inputError || isOverLimit ? 'has-error' : ''}`}
              placeholder={dialog.inputPrompt.placeholder}
              value={inputValue}
              onChange={handleInputChange}
              rows={3}
              disabled={busy}
            />
            {inputError && (
              <span className="dialog-input-error" role="alert">
                {inputError}
              </span>
            )}
          </div>
        )}

        <div className="dialog-actions">
          <button className="dash-button" onClick={onClose} disabled={busy}>
            {dialog.confirmLabel ? 'Cancel' : 'Close'}
          </button>
          {dialog.confirmLabel && (
            <button
              className={`dash-button ${isDanger ? 'danger' : 'primary'}`}
              disabled={cannotConfirm}
              onClick={handleConfirm}
            >
              {busy ? 'Working…' : dialog.confirmLabel}
            </button>
          )}
        </div>
      </section>
    </div>
  )
}

function Toast({ message, onClose }: { message: string; onClose: () => void }) {
  return <div className="toast-message" role="status"><Activity size={14} /><span>{message}</span><button aria-label="Dismiss message" onClick={onClose}>×</button></div>
}

function MetricCount({ label, value, note, icon: Icon }: { label: string; value: string; note: string; icon: LucideIcon }) {
  return <article className="dash-card recovery-count"><span className="recovery-count-icon"><Icon size={14} /></span><span className="recovery-count-label">{label}</span><strong>{value}</strong><small>{note}</small></article>
}

function isWithinDateRange(value: string, range: string) {
  if (range === 'all') return true
  const lower = value.toLowerCase()
  const timestamp = Date.parse(value)
  const age = Date.now() - timestamp
  if (range === '24h') return lower.includes('today') || (!Number.isNaN(timestamp) && age >= 0 && age <= 86_400_000)
  return lower.includes('today') || lower.includes('yesterday') || Number.isNaN(timestamp) || (age >= 0 && age <= 604_800_000)
}

export function DashboardView() {
  const pathname = usePathname()
  const { query, setQuery, environment, setEnvironment } = useDashboardControls()
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [toast, setToast] = useState('')
  const [busyId, setBusyId] = useState('')
  const [severityFilter, setSeverityFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [serviceFilter, setServiceFilter] = useState('all')
  const [incidentRange, setIncidentRange] = useState('all')

  const demoMode = isDemoMode
  const servicesResource = useSWR<Service[]>(demoMode ? 'demo-services' : 'services', () => demoMode ? Promise.resolve(demoServices) : servicesApi.list(), { fallbackData: demoMode ? demoServices : undefined, revalidateOnFocus: true, refreshInterval: demoMode ? 0 : 5000 })
  const incidentsResource = useSWR<Incident[]>(demoMode ? 'demo-incidents' : 'incidents', () => demoMode ? Promise.resolve(demoIncidents) : incidentsApi.list(), { fallbackData: demoMode ? demoIncidents : undefined, revalidateOnFocus: true, refreshInterval: demoMode ? 0 : 5000 })
  const recoveriesResource = useSWR<RecoveryAction[]>(demoMode ? 'demo-recoveries' : 'recoveries', () => demoMode ? Promise.resolve(demoRecoveries) : recoveriesApi.list(), { fallbackData: demoMode ? demoRecoveries : undefined, revalidateOnFocus: true, refreshInterval: demoMode ? 0 : 5000 })
  const analyticsResource = useSWR<AnalyticsSummary>(demoMode ? 'demo-analytics' : 'analytics', () => demoMode ? Promise.resolve(demoAnalytics) : analyticsApi.summary(), { fallbackData: demoMode ? demoAnalytics : undefined, revalidateOnFocus: true, refreshInterval: demoMode ? 0 : 10000 })
  const healthResource = useSWR<{ status: string }>(demoMode ? 'demo-health' : 'backend-health', () => demoMode ? Promise.resolve({ status: 'demo' }) : healthApi.get(), { fallbackData: demoMode ? { status: 'demo' } : undefined, revalidateOnFocus: false })
  const agentsResource = useSWR<InfrastructureAgent[]>(demoMode ? 'demo-agents' : 'agents', () => demoMode ? Promise.resolve(demoAgents) : agentsApi.list(), { fallbackData: demoMode ? demoAgents : undefined, revalidateOnFocus: false })
  const intelligenceOverviewResource = useSWR<IntelligenceOverview>(demoMode ? 'demo-intelligence-overview' : 'intelligence-overview', () => demoMode ? Promise.resolve(demoIntelligenceOverview) : intelligenceApi.overview(), { fallbackData: demoMode ? demoIntelligenceOverview : undefined, revalidateOnFocus: false })
  const predictionsResource = useSWR<Prediction[]>(demoMode ? 'demo-predictions' : 'predictions', () => demoMode ? Promise.resolve(demoPredictions) : intelligenceApi.predictions(), { fallbackData: demoMode ? demoPredictions : undefined, revalidateOnFocus: false })
  const anomaliesResource = useSWR<Anomaly[]>(demoMode ? 'demo-anomalies' : 'anomalies', () => demoMode ? Promise.resolve(demoAnomalies) : intelligenceApi.anomalies(), { fallbackData: demoMode ? demoAnomalies : undefined, revalidateOnFocus: false })
  const riskScoresResource = useSWR<ServiceRisk[]>(demoMode ? 'demo-risk-scores' : 'risk-scores', () => demoMode ? Promise.resolve(demoRiskScores) : intelligenceApi.riskScores(), { fallbackData: demoMode ? demoRiskScores : undefined, revalidateOnFocus: false })
  const recommendationsResource = useSWR<PreventiveRecommendation[]>(demoMode ? 'demo-recommendations' : 'recommendations', () => demoMode ? Promise.resolve(demoRecommendations) : intelligenceApi.preventiveRecommendations(), { fallbackData: demoMode ? demoRecommendations : undefined, revalidateOnFocus: false })
  const correlationsResource = useSWR<IncidentCorrelationGroup[]>(demoMode ? 'demo-correlations' : 'correlations', () => demoMode ? Promise.resolve(demoCorrelations) : intelligenceApi.correlations(), { fallbackData: demoMode ? demoCorrelations : undefined, revalidateOnFocus: false })
  const evaluationsResource = useSWR<ModelEvaluationMetric[]>(demoMode ? 'demo-evaluations' : 'evaluations', () => demoMode ? Promise.resolve(demoEvaluations) : intelligenceApi.modelEvaluations(), { fallbackData: demoMode ? demoEvaluations : undefined, revalidateOnFocus: false })

  // Real-time Server-Sent Events (SSE) updates
  useRealtimeEvents({
    onIncidentCreated: (data) => {
      setToast(`Alert: ${data.id} created on ${data.serviceName}`)
      incidentsResource.mutate()
      analyticsResource.mutate()
      servicesResource.mutate()
    },
    onIncidentUpdated: () => {
      incidentsResource.mutate()
      analyticsResource.mutate()
    },
    onRecoveryUpdated: () => {
      recoveriesResource.mutate()
      incidentsResource.mutate()
      servicesResource.mutate()
    },
    onServiceHealth: () => {
      servicesResource.mutate()
    },
  }, !demoMode)

  const parts = pathname.replace(/^\/dashboard\/?/, '').split('/').filter(Boolean)
  const page = parts[0] ?? 'overview'
  const detailId = parts[1] ? decodeURIComponent(parts[1]) : ''
  const incidentDetailResource = useSWR<Incident>(!demoMode && page === 'incidents' && detailId ? ['incident', detailId] : null, () => incidentsApi.get(detailId), { revalidateOnFocus: false })
  const services = useMemo(() => servicesResource.data ?? [], [servicesResource.data])
  const incidents = useMemo(() => incidentsResource.data ?? [], [incidentsResource.data])
  const recoveries = useMemo(() => recoveriesResource.data ?? [], [recoveriesResource.data])
  const agents = useMemo(() => agentsResource.data ?? [], [agentsResource.data])
  const analytics = analyticsResource.data
  const globalQuery = query.trim().toLowerCase()
  const filteredServices = useMemo(() => services.filter((service) => (environment === 'all' || service.environment === environment) && `${service.name} ${service.environment} ${service.status} ${service.id}`.toLowerCase().includes(globalQuery)), [services, environment, globalQuery])
  const filteredIncidents = useMemo(() => incidents.filter((incident) => `${incident.id} ${incident.title} ${incident.serviceName} ${incident.status} ${incident.severity}`.toLowerCase().includes(globalQuery)), [incidents, globalQuery])
  const filteredRecoveries = useMemo(() => recoveries.filter((item) => `${item.id} ${item.incidentId} ${item.serviceName} ${item.action} ${item.status}`.toLowerCase().includes(globalQuery)), [recoveries, globalQuery])
  const filteredAgents = useMemo(() => agents.filter((agent) => (environment === 'all' || agent.environment === environment) && `${agent.name} ${agent.hostname} ${agent.status} ${agent.id}`.toLowerCase().includes(globalQuery)), [agents, environment, globalQuery])
  const incidentForDetail = incidents.find((item) => item.id === detailId) ?? incidentDetailResource.data
  const serviceForDetail = services.find((item) => item.id === detailId)

  const heading = (title: string, description: string, action?: React.ReactNode) => <div className="dashboard-heading"><div><h1>{title}</h1><p>{description}</p></div>{action && <div className="dashboard-toolbar">{action}</div>}</div>
  const notice = <div className={`notice-strip ${demoMode ? '' : 'live-notice'}`}><strong>{demoMode ? 'Read-only demonstration.' : 'Backend connection configured.'}</strong> {demoMode ? 'All displayed service names, incidents, metrics, and recovery outcomes are illustrative. No infrastructure is connected.' : 'Requests use the configured API. Values are shown only when returned by the backend.'}</div>
  const refreshData = async () => {
    if (!demoMode) {
      try {
        await servicesApi.check()
      } catch {
        // Continue revalidation even if live check endpoint encounters network delay
      }
    }
    await Promise.all([
      servicesResource.mutate(),
      incidentsResource.mutate(),
      recoveriesResource.mutate(),
      analyticsResource.mutate(),
      healthResource.mutate(),
      agentsResource.mutate(),
    ])
  }

  async function performApproval(id: string) {
    setBusyId(id)
    try {
      const result = await recoveriesApi.approve(id)
      await Promise.all([recoveriesResource.mutate(), incidentsResource.mutate()])
      setToast(`Approval response received: ${result.status}. No completion is assumed until verification is returned.`)
    } catch (error) {
      setDialog({ title: 'Approval was not completed', description: error instanceof Error ? error.message : 'The backend rejected the request. No recovery state was changed in the interface.' })
    } finally {
      setBusyId('')
    }
  }

  function beginApproval(id: string) {
    const action = recoveries.find((item) => item.id === id)
    if (demoMode) {
      setDialog({ title: 'Demo actions are read-only', description: 'No approval was sent and no infrastructure operation ran. Connect a backend to use real recovery controls.' })
      return
    }
    setDialog({ title: 'Approve recovery action?', description: `This submits approval for ${action?.action ?? 'this action'} on ${action?.serviceName ?? 'the selected service'}. The backend policy remains authoritative.`, confirmLabel: 'Approve action', onConfirm: () => performApproval(id) })
  }

  async function performRejection(id: string, reason?: string) {
    setBusyId(id)
    try {
      const trimmedReason = reason?.trim() ? reason.trim() : undefined
      const result = await recoveriesApi.reject(id, trimmedReason)
      await Promise.all([recoveriesResource.mutate(), incidentsResource.mutate()])
      setToast(
        trimmedReason
          ? `Recovery action was rejected: ${result.action} ("${trimmedReason}")`
          : `Recovery action was rejected: ${result.status}.`
      )
    } catch (error) {
      setDialog({ title: 'Rejection was not completed', description: error instanceof Error ? error.message : 'The backend rejected the request.' })
    } finally {
      setBusyId('')
    }
  }

  function beginRejection(id: string) {
    const action = recoveries.find((item) => item.id === id)
    if (demoMode) {
      setDialog({ title: 'Demo actions are read-only', description: 'No infrastructure operation ran. Connect a backend to reject real recovery controls.' })
      return
    }
    setDialog({
      title: 'Reject recovery action?',
      description: `Provide an optional operational reason for declining ${action?.action ?? 'this remediation'} on ${action?.serviceName ?? 'the service'}. This will be logged in the immutable audit log.`,
      confirmLabel: 'Reject action',
      confirmTone: 'danger',
      inputPrompt: {
        label: 'Rejection reason (optional)',
        placeholder: 'Specify why this remediation was declined (e.g. Maintenance in progress, manual mitigation preferred, false alarm)...',
        maxLength: 500,
      },
      onConfirm: async (inputValue) => {
        await performRejection(id, inputValue)
      },
    })
  }

  async function performRecoveryRequest(id: string) {
    setBusyId(id)
    try {
      const result = await incidentsApi.requestRecovery(id)
      await Promise.all([recoveriesResource.mutate(), incidentsResource.mutate()])
      setToast(`Recovery request recorded by the backend as ${result.status}. Verification is still required.`)
    } catch (error) {
      setDialog({ title: 'Recovery request was not completed', description: error instanceof Error ? error.message : 'The backend rejected the request. No recovery was reported as successful.' })
    } finally {
      setBusyId('')
    }
  }

  function beginRecoveryRequest(incident: Incident) {
    if (demoMode) {
      setDialog({ title: 'Demo actions are read-only', description: 'No infrastructure action ran. Connect the FastAPI recovery endpoint before requesting a real recovery.' })
      return
    }
    setDialog({ title: 'Request controlled recovery?', description: `Submit a recovery request for ${incident.serviceName}. The backend validates policy and approval requirements; this request does not mean recovery is complete.`, confirmLabel: 'Submit request', onConfirm: () => performRecoveryRequest(incident.id) })
  }

  async function performExecution(id: string) {
    setBusyId(id)
    try {
      const result = await recoveriesApi.execute(id)
      await Promise.all([recoveriesResource.mutate(), incidentsResource.mutate(), servicesResource.mutate()])
      setToast(`Recovery action executed: ${result.action} is ${result.status} (verification: ${result.verification}).`)
    } catch (error) {
      setDialog({ title: 'Execution was not completed', description: error instanceof Error ? error.message : 'The backend rejected the recovery execution.' })
    } finally {
      setBusyId('')
    }
  }

  function beginExecution(id: string) {
    const action = recoveries.find((item) => item.id === id)
    if (demoMode) {
      setDialog({ title: 'Demo actions are read-only', description: 'Connect a backend to execute real recovery actions.' })
      return
    }
    setDialog({
      title: 'Execute recovery action?',
      description: `Trigger execution of ${action?.action ?? 'this action'} on ${action?.serviceName ?? 'the selected service'} with automated health verification.`,
      confirmLabel: 'Execute action',
      onConfirm: () => performExecution(id),
    })
  }

  async function performRevocation(id: string) {
    setBusyId(id)
    try {
      await agentsApi.revoke(id)
      await agentsResource.mutate()
      setToast(`Agent ${id} has been revoked.`)
    } catch (error) {
      setDialog({ title: 'Agent revocation failed', description: error instanceof Error ? error.message : 'The backend rejected the revocation request.' })
    } finally {
      setBusyId('')
    }
  }

  function beginRevocation(id: string) {
    if (demoMode) {
      setDialog({ title: 'Demo actions are read-only', description: 'Agent revocation requires a live backend connection.' })
      return
    }
    setDialog({
      title: 'Revoke agent credentials?',
      description: `This immediately revokes authentication keys for agent ${id}. The agent will no longer be able to execute recovery operations or report heartbeats.`,
      confirmLabel: 'Revoke agent',
      onConfirm: () => performRevocation(id),
    })
  }

  async function downloadReport(id: string, format: 'pdf' | 'json' = 'pdf') {
    if (demoMode) {
      setDialog({
        title: 'Backend connection required',
        description: `Generating ${format.toUpperCase()} incident reports requires an active FastAPI backend (GET /api/v1/incidents/${id}/report?format=${format}). Configure NEXT_PUBLIC_API_BASE_URL to download live reports.`,
      })
      return
    }
    setBusyId(`${id}-${format}`)
    try {
      const blob = await incidentsApi.downloadReport(id, format)
      const fileUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = fileUrl
      anchor.download = `${id}-report.${format}`
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(fileUrl), 1000)
      setToast(`Report download completed for ${id} (${format.toUpperCase()}).`)
    } catch (error) {
      setDialog({
        title: `Could not download ${format.toUpperCase()} report`,
        description: error instanceof Error ? error.message : 'The backend did not return a report.',
      })
    } finally {
      setBusyId('')
    }
  }

  async function handleRecommendationStatusUpdate(id: string, status: string) {
    if (demoMode) {
      setToast(`Recommendation updated to ${status} (Demo)`)
      return
    }
    try {
      await intelligenceApi.updateRecommendationStatus(id, status)
      setToast(`Recommendation marked as ${status}`)
      recommendationsResource.mutate()
      intelligenceOverviewResource.mutate()
    } catch {
      setToast('Failed to update recommendation status.')
    }
  }

  const matchingIncidents = filteredIncidents.filter((incident) => (severityFilter === 'all' || incident.severity === severityFilter) && (statusFilter === 'all' || incident.status === statusFilter) && (serviceFilter === 'all' || incident.serviceId === serviceFilter) && isWithinDateRange(incident.detectedAt, incidentRange))
  const commonNotices = notice
  const dialogLayer = dialog && <ConfirmDialog dialog={dialog} onClose={() => setDialog(null)} busy={busyId !== ''} />
  const toastLayer = toast && <Toast message={toast} onClose={() => setToast('')} />

  if (page === 'services' && detailId) {
    const serviceLoading = !demoMode && servicesResource.isLoading
    const serviceError = servicesResource.error
    return (
      <>
        {commonNotices}
        {heading(
          serviceForDetail?.name ?? (serviceLoading ? 'Loading service...' : 'Service details'),
          serviceForDetail
            ? `Service health and associated activity · ${serviceForDetail.environment}`
            : serviceLoading
            ? 'Retrieving service telemetry from the backend API.'
            : 'This service is not present in the available data.',
          <Link className="dash-button" href="/dashboard/services">
            <ArrowDownRight size={12} />All services
          </Link>
        )}
        {serviceLoading ? (
          <div className="metric-grid metric-grid-six">
            <MetricCardSkeleton tone="teal" />
            <MetricCardSkeleton tone="violet" />
            <MetricCardSkeleton tone="teal" />
            <MetricCardSkeleton tone="amber" />
            <MetricCardSkeleton tone="teal" />
            <MetricCardSkeleton tone="teal" />
          </div>
        ) : serviceError ? (
          <SectionErrorState
            title={`Failed to load service ${detailId}`}
            error={serviceError}
            onRetry={() => servicesResource.mutate()}
          />
        ) : serviceForDetail ? (
          <ServiceDetailView
            service={serviceForDetail}
            incidents={incidents}
            recoveries={recoveries}
            incidentsLoading={!demoMode && incidentsResource.isLoading}
            incidentsError={incidentsResource.error}
            onRetryIncidents={() => incidentsResource.mutate()}
            recoveriesLoading={!demoMode && recoveriesResource.isLoading}
            recoveriesError={recoveriesResource.error}
            onRetryRecoveries={() => recoveriesResource.mutate()}
          />
        ) : (
          <EmptyState
            title="Service not found"
            detail={`No service with ID "${detailId}" exists in the current environment.`}
            icon={Server}
          />
        )}
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'incidents' && detailId) {
    const incidentLoading = !demoMode && incidentDetailResource.isLoading
    const incidentError = incidentDetailResource.error
    const isPdfBusy = busyId === `${detailId}-pdf`
    const isJsonBusy = busyId === `${detailId}-json`
    const isBusy = Boolean(busyId)

    return (
      <>
        {commonNotices}
        {heading(
          incidentForDetail?.id ?? (incidentLoading ? 'Loading incident...' : 'Incident details'),
          incidentForDetail?.title ?? (incidentLoading ? 'Retrieving incident diagnosis from the backend API.' : 'This incident is not present in the available data.'),
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center' }}>
            {incidentForDetail && (
              <>
                <button
                  className="dash-button"
                  disabled={isBusy}
                  onClick={() => downloadReport(incidentForDetail.id, 'pdf')}
                  title="Download post-mortem PDF report"
                  aria-label="Download PDF report"
                >
                  {isPdfBusy ? <RefreshCw size={12} className="spin" /> : <Download size={12} />}
                  {isPdfBusy ? 'Preparing PDF…' : 'Download PDF Report'}
                </button>
                <button
                  className="dash-button"
                  disabled={isBusy}
                  onClick={() => downloadReport(incidentForDetail.id, 'json')}
                  title="Download structured JSON report"
                  aria-label="Download JSON report"
                >
                  {isJsonBusy ? <RefreshCw size={12} className="spin" /> : <FileText size={12} />}
                  {isJsonBusy ? 'Preparing JSON…' : 'Download JSON Report'}
                </button>
              </>
            )}
            <Link className="dash-button" href="/dashboard/incidents">
              <ArrowDownRight size={12} />All incidents
            </Link>
          </div>
        )}
        {incidentLoading ? (
          <div className="incident-detail-grid">
            <div className="dash-card panel"><ListSkeleton count={4} /></div>
            <div className="dash-card panel"><ListSkeleton count={4} /></div>
          </div>
        ) : incidentError ? (
          <SectionErrorState
            title={`Failed to load incident ${detailId}`}
            error={incidentError}
            onRetry={() => incidentDetailResource.mutate()}
          />
        ) : incidentForDetail ? (
          <>
            <IncidentDetailView
              incident={incidentForDetail}
              onRequestRecovery={() => beginRecoveryRequest(incidentForDetail)}
              onDownloadReport={downloadReport}
              busyId={busyId}
            />
            <IncidentCollaborationPanel
              incident={incidentForDetail}
              demoMode={demoMode}
              onIncidentUpdated={() => {
                incidentsResource.mutate()
                incidentDetailResource.mutate()
              }}
            />
          </>
        ) : (
          <EmptyState
            title="Incident not found"
            detail={`No incident with ID "${detailId}" exists in the available records.`}
            icon={CircleAlert}
          />
        )}
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'services') {
    const servicesLoading = !demoMode && servicesResource.isLoading
    return (
      <>
        {commonNotices}
        {heading(
          'Services',
          'Monitor health, availability, latency, and error rate across environments.',
          <span className="demo-label">
            {servicesLoading ? 'Checking services...' : `${filteredServices.length} services in view`}
          </span>
        )}
        <section className="dash-card panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Service inventory</h2>
              <p className="panel-subtitle">Select a column heading to sort. Search and environment filters are in the top bar.</p>
            </div>
          </div>
          <ServiceTable
            services={filteredServices}
            loading={servicesLoading}
            error={servicesResource.error}
            onRetry={() => servicesResource.mutate()}
            filterQuery={query}
            onClearFilter={() => {
              setQuery('')
              setEnvironment('all')
            }}
          />
        </section>
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'incidents') {
    const incidentsLoading = !demoMode && incidentsResource.isLoading
    const filterActive = severityFilter !== 'all' || statusFilter !== 'all' || serviceFilter !== 'all' || incidentRange !== 'all' || query.trim() !== ''
    return (
      <>
        {commonNotices}
        {heading(
          'Incident management',
          'Inspect severity, service impact, diagnosis, and recovery state.',
          <span className="demo-label">
            {incidentsLoading ? 'Loading incidents...' : `${matchingIncidents.length} incidents`}
          </span>
        )}
        <div className="search-filter incident-filters">
          <label>
            <span>Severity</span>
            <select className="small-select" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} disabled={incidentsLoading}>
              <option value="all">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </select>
          </label>
          <label>
            <span>Status</span>
            <select className="small-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} disabled={incidentsLoading}>
              <option value="all">All statuses</option>
              <option value="open">Open</option>
              <option value="investigating">Investigating</option>
              <option value="recovering">Recovering</option>
              <option value="resolved">Resolved</option>
            </select>
          </label>
          <label>
            <span>Service</span>
            <select className="small-select" value={serviceFilter} onChange={(event) => setServiceFilter(event.target.value)} disabled={incidentsLoading || !services.length}>
              <option value="all">All services</option>
              {services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}
            </select>
          </label>
          <label>
            <span>Date</span>
            <select className="small-select" value={incidentRange} onChange={(event) => setIncidentRange(event.target.value)} disabled={incidentsLoading}>
              <option value="all">All dates</option>
              <option value="24h">Last 24 hours</option>
              <option value="7d">Last 7 days</option>
            </select>
          </label>
        </div>
        <section className="dash-card panel">
          <IncidentTable
            incidents={matchingIncidents}
            loading={incidentsLoading}
            error={incidentsResource.error}
            onRetry={() => incidentsResource.mutate()}
            filterActive={filterActive}
            onClearFilter={() => {
              setSeverityFilter('all')
              setStatusFilter('all')
              setServiceFilter('all')
              setIncidentRange('all')
              setQuery('')
            }}
          />
        </section>
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'recovery' || page === 'recoveries') {
    const recoveriesLoading = !demoMode && recoveriesResource.isLoading
    const pending = filteredRecoveries.filter((item) => item.status === 'pending_approval').length
    const approved = filteredRecoveries.filter((item) => item.status === 'approved').length
    const running = filteredRecoveries.filter((item) => item.status === 'running').length
    const completed = filteredRecoveries.filter((item) => item.status === 'completed').length
    const failed = filteredRecoveries.filter((item) => item.status === 'failed').length
    return (
      <>
        {commonNotices}
        {heading('Recovery center', 'Review policy-gated operations and verify status returned by the backend.')}
        <div className="metric-grid metric-grid-five">
          {recoveriesLoading ? (
            <>
              <MetricCardSkeleton tone="amber" />
              <MetricCardSkeleton tone="teal" />
              <MetricCardSkeleton tone="teal" />
              <MetricCardSkeleton tone="teal" />
              <MetricCardSkeleton tone="amber" />
            </>
          ) : (
            <>
              <MetricCount label="Pending approval" value={String(pending).padStart(2, '0')} note="Requires review" icon={Clock3} />
              <MetricCount label="Approved" value={String(approved).padStart(2, '0')} note="Awaiting execution" icon={CheckCircle2} />
              <MetricCount label="Running" value={String(running).padStart(2, '0')} note="Backend-reported" icon={RefreshCw} />
              <MetricCount label="Completed" value={String(completed).padStart(2, '0')} note="Verification required" icon={ShieldCheck} />
              <MetricCount label="Failed" value={String(failed).padStart(2, '0')} note="Needs escalation" icon={ArrowDownRight} />
            </>
          )}
        </div>
        <section className="dash-card panel" style={{ marginTop: 13 }}>
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Recovery queue</h2>
              <p className="panel-subtitle">Review policy-governed actions, approve safe remediations, and trigger automated verification.</p>
            </div>
          </div>
          <RecoveryTable
            actions={filteredRecoveries}
            allowControls
            loading={recoveriesLoading}
            error={recoveriesResource.error}
            onRetry={() => recoveriesResource.mutate()}
            filterActive={Boolean(query.trim())}
            onClearFilter={() => setQuery('')}
            onApprove={beginApproval}
            onReject={beginRejection}
            onExecute={beginExecution}
          />
        </section>
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'history') {
    const recoveriesLoading = !demoMode && recoveriesResource.isLoading
    const history = filteredRecoveries.filter((item) => item.status === 'completed' || item.status === 'failed' || item.status === 'rejected')
    return (
      <>
        {commonNotices}
        {heading(
          'Recovery history',
          'Review completed and failed actions, timing, result, and verification state.',
          <span className="demo-label">
            {recoveriesLoading ? 'Loading history...' : `${history.length} records`}
          </span>
        )}
        <section className="dash-card panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Recorded operations</h2>
              <p className="panel-subtitle">An action is only successful when the backend confirms completion and verification.</p>
            </div>
          </div>
          <RecoveryTable
            actions={history}
            loading={recoveriesLoading}
            error={recoveriesResource.error}
            onRetry={() => recoveriesResource.mutate()}
            filterActive={Boolean(query.trim())}
            onClearFilter={() => setQuery('')}
          />
        </section>
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'monitoring') {
    return (
      <>
        {commonNotices}
        <MonitoringView
          services={filteredServices}
          loading={!demoMode && servicesResource.isLoading}
          error={servicesResource.error}
          onRetry={() => servicesResource.mutate()}
        />
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'analytics') {
    return (
      <>
        {commonNotices}
        <AnalyticsView
          analytics={analytics}
          services={filteredServices}
          incidents={filteredIncidents}
          recoveries={filteredRecoveries}
          demoMode={demoMode}
          loading={!demoMode && analyticsResource.isLoading}
          error={analyticsResource.error}
          onRetry={() => analyticsResource.mutate()}
        />
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'experiments' || page === 'benchmarks') {
    return (
      <>
        {commonNotices}
        <ExperimentsView demoMode={demoMode} />
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'reports') {
    return (
      <>
        {commonNotices}
        <ReportsView
          incidents={filteredIncidents}
          demoMode={demoMode}
          onDownload={downloadReport}
          busyId={busyId}
          loading={!demoMode && incidentsResource.isLoading}
          error={incidentsResource.error}
          onRetry={() => incidentsResource.mutate()}
        />
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'intelligence') {
    return (
      <>
        {commonNotices}
        <IntelligenceView
          overview={intelligenceOverviewResource.data}
          predictions={predictionsResource.data ?? demoPredictions}
          anomalies={anomaliesResource.data ?? demoAnomalies}
          riskScores={riskScoresResource.data ?? demoRiskScores}
          recommendations={recommendationsResource.data ?? demoRecommendations}
          correlations={correlationsResource.data ?? demoCorrelations}
          evaluations={evaluationsResource.data ?? demoEvaluations}
          demoMode={demoMode}
          onStatusUpdate={handleRecommendationStatusUpdate}
        />
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'agents') {
    const agentsLoading = !demoMode && agentsResource.isLoading
    return (
      <>
        {commonNotices}
        {heading(
          'Infrastructure agents',
          'Monitor distributed host agents, mTLS credentials, and execution capabilities.',
          <span className="demo-label">
            {agentsLoading ? 'Checking agents...' : `${filteredAgents.length} agents registered`}
          </span>
        )}
        <AgentsView
          agents={filteredAgents}
          demoMode={demoMode}
          onRevoke={beginRevocation}
          busyId={busyId}
          loading={agentsLoading}
          error={agentsResource.error}
          onRetry={() => agentsResource.mutate()}
          filterActive={Boolean(query.trim() || environment !== 'all')}
          onClearFilter={() => {
            setQuery('')
            setEnvironment('all')
          }}
        />
        {dialogLayer}
        {toastLayer}
      </>
    )
  }

  if (page === 'notifications') {
    return <>{commonNotices}<NotificationsView demoMode={demoMode} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'releases' || page === 'canary') {
    return <>{commonNotices}<CanaryReleasesView demoMode={demoMode} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'timeline') {
    return <>{commonNotices}<OperationsTimelineView demoMode={demoMode} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'security' || page === 'sso') {
    return <>{commonNotices}<SecurityCenterView demoMode={demoMode} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'observability' || page === 'traces') {
    return <>{commonNotices}<ObservabilityCenterView demoMode={demoMode} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'settings') {
    return <>{commonNotices}<SettingsView demoMode={demoMode} healthStatus={healthResource.data?.status} />{dialogLayer}{toastLayer}</>
  }

  if (page !== 'overview') {
    return <>{commonNotices}{heading('Page not found', 'Choose a workspace area from the navigation.', <Link className="dash-button" href="/dashboard"><ArrowDownRight size={12} />Overview</Link>)}{dialogLayer}{toastLayer}</>
  }

  return (
    <>
      {commonNotices}
      <OverviewView
        services={filteredServices}
        incidents={filteredIncidents}
        recoveries={filteredRecoveries}
        analytics={analytics}
        demoMode={demoMode}
        onRefresh={refreshData}
        servicesLoading={!demoMode && servicesResource.isLoading}
        servicesError={servicesResource.error}
        onRetryServices={() => servicesResource.mutate()}
        incidentsLoading={!demoMode && incidentsResource.isLoading}
        incidentsError={incidentsResource.error}
        onRetryIncidents={() => incidentsResource.mutate()}
        recoveriesLoading={!demoMode && recoveriesResource.isLoading}
        recoveriesError={recoveriesResource.error}
        onRetryRecoveries={() => recoveriesResource.mutate()}
        analyticsLoading={!demoMode && analyticsResource.isLoading}
        analyticsError={analyticsResource.error}
        onRetryAnalytics={() => analyticsResource.mutate()}
      />
      {dialogLayer}
      {toastLayer}
    </>
  )
}
