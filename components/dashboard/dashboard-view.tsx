'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import useSWR from 'swr'
import type { LucideIcon } from 'lucide-react'
import { Activity, ArrowDownRight, CheckCircle2, Clock3, RefreshCw, ShieldCheck } from 'lucide-react'
import type { AnalyticsSummary, Incident, RecoveryAction, Service } from '@/types'
import { isApiConfigured } from '@/lib/api/client'
import { analyticsApi, healthApi, incidentsApi, recoveriesApi, servicesApi } from '@/lib/api/resources'
import { demoAnalytics, demoIncidents, demoRecoveries, demoServices } from '@/lib/demo/mock-data'
import { useDashboardControls } from '@/components/dashboard/dashboard-shell'
import { AnalyticsView, IncidentTable, IncidentDetailView, MonitoringView, OverviewView, RecoveryTable, ReportsView, ServiceDetailView, ServiceTable, SettingsView } from '@/components/dashboard/data-views'

type DialogState = { title: string; description: string; confirmLabel?: string; onConfirm?: () => Promise<void> | void }

function ConfirmDialog({ dialog, onClose, busy }: { dialog: DialogState; onClose: () => void; busy: boolean }) {
  const panelRef = useRef<HTMLElement>(null)
  const closeRef = useRef(onClose)

  useEffect(() => { closeRef.current = onClose }, [onClose])
  useEffect(() => {
    const panel = panelRef.current
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const focusable = panel ? Array.from(panel.querySelectorAll<HTMLElement>('button:not(:disabled)')) : []
    ;(focusable[0] ?? panel)?.focus()
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

  return <div className="dialog-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose() }}><section ref={panelRef} tabIndex={-1} className="dialog-card" role="dialog" aria-modal="true" aria-labelledby="dialog-title" aria-describedby="dialog-description"><div className="dialog-icon"><ShieldCheck size={17} /></div><h2 id="dialog-title">{dialog.title}</h2><p id="dialog-description">{dialog.description}</p><div className="dialog-actions"><button className="dash-button" onClick={onClose} disabled={busy}>{dialog.confirmLabel ? 'Cancel' : 'Close'}</button>{dialog.confirmLabel && <button className="dash-button primary" disabled={busy} onClick={async () => { const action = dialog.onConfirm; onClose(); await action?.() }}>{busy ? 'Working…' : dialog.confirmLabel}</button>}</div></section></div>
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
  const { query, environment } = useDashboardControls()
  const [dialog, setDialog] = useState<DialogState | null>(null)
  const [toast, setToast] = useState('')
  const [busyId, setBusyId] = useState('')
  const [severityFilter, setSeverityFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [serviceFilter, setServiceFilter] = useState('all')
  const [incidentRange, setIncidentRange] = useState('all')

  const demoMode = !isApiConfigured
  const servicesResource = useSWR<Service[]>(demoMode ? 'demo-services' : 'services', () => demoMode ? Promise.resolve(demoServices) : servicesApi.list(), { fallbackData: demoMode ? demoServices : undefined, revalidateOnFocus: false })
  const incidentsResource = useSWR<Incident[]>(demoMode ? 'demo-incidents' : 'incidents', () => demoMode ? Promise.resolve(demoIncidents) : incidentsApi.list(), { fallbackData: demoMode ? demoIncidents : undefined, revalidateOnFocus: false })
  const recoveriesResource = useSWR<RecoveryAction[]>(demoMode ? 'demo-recoveries' : 'recoveries', () => demoMode ? Promise.resolve(demoRecoveries) : recoveriesApi.list(), { fallbackData: demoMode ? demoRecoveries : undefined, revalidateOnFocus: false })
  const analyticsResource = useSWR<AnalyticsSummary>(demoMode ? 'demo-analytics' : 'analytics', () => demoMode ? Promise.resolve(demoAnalytics) : analyticsApi.summary(), { fallbackData: demoMode ? demoAnalytics : undefined, revalidateOnFocus: false })
  const healthResource = useSWR<{ status: string }>(demoMode ? 'demo-health' : 'backend-health', () => demoMode ? Promise.resolve({ status: 'demo' }) : healthApi.get(), { fallbackData: demoMode ? { status: 'demo' } : undefined, revalidateOnFocus: false })

  const parts = pathname.replace(/^\/dashboard\/?/, '').split('/').filter(Boolean)
  const page = parts[0] ?? 'overview'
  const detailId = parts[1] ? decodeURIComponent(parts[1]) : ''
  const incidentDetailResource = useSWR<Incident>(!demoMode && page === 'incidents' && detailId ? ['incident', detailId] : null, () => incidentsApi.get(detailId), { revalidateOnFocus: false })
  const services = servicesResource.data ?? []
  const incidents = incidentsResource.data ?? []
  const recoveries = recoveriesResource.data ?? []
  const analytics = analyticsResource.data
  const apiErrors = [servicesResource.error, incidentsResource.error, recoveriesResource.error, analyticsResource.error, healthResource.error, incidentDetailResource.error].filter(Boolean)
  const loading = !demoMode && [servicesResource, incidentsResource, recoveriesResource, analyticsResource, healthResource].some((resource) => resource.isLoading)
  const globalQuery = query.trim().toLowerCase()
  const filteredServices = useMemo(() => services.filter((service) => (environment === 'all' || service.environment === environment) && `${service.name} ${service.environment} ${service.status} ${service.id}`.toLowerCase().includes(globalQuery)), [services, environment, globalQuery])
  const filteredIncidents = useMemo(() => incidents.filter((incident) => `${incident.id} ${incident.title} ${incident.serviceName} ${incident.status} ${incident.severity}`.toLowerCase().includes(globalQuery)), [incidents, globalQuery])
  const filteredRecoveries = useMemo(() => recoveries.filter((item) => `${item.id} ${item.incidentId} ${item.serviceName} ${item.action} ${item.status}`.toLowerCase().includes(globalQuery)), [recoveries, globalQuery])
  const incidentForDetail = incidents.find((item) => item.id === detailId) ?? incidentDetailResource.data
  const serviceForDetail = services.find((item) => item.id === detailId)

  const heading = (title: string, description: string, action?: React.ReactNode) => <div className="dashboard-heading"><div><h1>{title}</h1><p>{description}</p></div>{action && <div className="dashboard-toolbar">{action}</div>}</div>
  const notice = <div className={`notice-strip ${demoMode ? '' : 'live-notice'}`}><strong>{demoMode ? 'Read-only demonstration.' : 'Backend connection configured.'}</strong> {demoMode ? 'All displayed service names, incidents, metrics, and recovery outcomes are illustrative. No infrastructure is connected.' : 'Requests use the configured API. Values are shown only when returned by the backend.'}</div>
  const refreshData = async () => { await Promise.all([servicesResource.mutate(), incidentsResource.mutate(), recoveriesResource.mutate(), analyticsResource.mutate(), healthResource.mutate()]) }

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

  function beginRejection() {
    setDialog({ title: 'Rejection endpoint unavailable', description: 'The current backend contract does not include a recovery rejection endpoint. Nothing was sent and the action state was not changed.' })
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

  async function downloadReport(id: string) {
    if (demoMode) return
    setBusyId(id)
    try {
      const blob = await incidentsApi.downloadReport(id)
      const fileUrl = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = fileUrl
      anchor.download = `${id}-report.${blob.type.includes('pdf') ? 'pdf' : blob.type.includes('json') ? 'json' : 'bin'}`
      document.body.append(anchor)
      anchor.click()
      anchor.remove()
      window.setTimeout(() => URL.revokeObjectURL(fileUrl), 1000)
      setToast(`Report download started for ${id}.`)
    } catch (error) {
      setDialog({ title: 'Report could not be downloaded', description: error instanceof Error ? error.message : 'The backend did not return a report.' })
    } finally {
      setBusyId('')
    }
  }

  const matchingIncidents = filteredIncidents.filter((incident) => (severityFilter === 'all' || incident.severity === severityFilter) && (statusFilter === 'all' || incident.status === statusFilter) && (serviceFilter === 'all' || incident.serviceId === serviceFilter) && isWithinDateRange(incident.detectedAt, incidentRange))
  const commonNotices = <>{notice}{loading && <div className="notice-strip live-notice" role="status">Loading current backend data. Sample values are not substituted in live mode.</div>}{apiErrors.length > 0 && <div className="error-strip" role="alert"><strong>Backend data could not be loaded.</strong> {apiErrors[0] instanceof Error ? apiErrors[0].message : 'Request failed. Check the API URL and server response.'} Sample values are not substituted in live mode. <button className="table-sort" onClick={refreshData}>Retry</button></div>}</>
  const dialogLayer = dialog && <ConfirmDialog dialog={dialog} onClose={() => setDialog(null)} busy={busyId !== ''} />
  const toastLayer = toast && <Toast message={toast} onClose={() => setToast('')} />

  if (page === 'services' && detailId) {
    return <>{commonNotices}{heading(serviceForDetail?.name ?? 'Service details', serviceForDetail ? `Service health and associated activity · ${serviceForDetail.environment}` : loading ? 'Loading service details from the backend.' : 'This service is not present in the available data.', <Link className="dash-button" href="/dashboard/services"><ArrowDownRight size={12} />All services</Link>)}{serviceForDetail && <ServiceDetailView service={serviceForDetail} incidents={incidents} recoveries={recoveries} />}{dialogLayer}{toastLayer}</>
  }

  if (page === 'incidents' && detailId) {
    return <>{commonNotices}{heading(incidentForDetail?.id ?? 'Incident details', incidentForDetail?.title ?? (loading ? 'Loading incident details from the backend.' : 'This incident is not present in the available data.'), <Link className="dash-button" href="/dashboard/incidents"><ArrowDownRight size={12} />All incidents</Link>)}{incidentForDetail && <IncidentDetailView incident={incidentForDetail} onRequestRecovery={() => beginRecoveryRequest(incidentForDetail)} />}{!incidentForDetail && !loading && <div className="dash-card panel"><p className="panel-subtitle">The selected incident was not found.</p></div>}{dialogLayer}{toastLayer}</>
  }

  if (page === 'services') {
    return <>{commonNotices}{heading('Services', 'Monitor health, availability, latency, and error rate across environments.', <span className="demo-label">{filteredServices.length} services in view</span>)}<section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Service inventory</h2><p className="panel-subtitle">Select a column heading to sort. Search and environment filters are in the top bar.</p></div></div><ServiceTable services={filteredServices} /></section>{dialogLayer}{toastLayer}</>
  }

  if (page === 'incidents') {
    return <>{commonNotices}{heading('Incident management', 'Inspect severity, service impact, diagnosis, and recovery state.', <span className="demo-label">{matchingIncidents.length} incidents</span>)}<div className="search-filter incident-filters"><label><span>Severity</span><select className="small-select" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)}><option value="all">All severities</option><option value="critical">Critical</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label><label><span>Status</span><select className="small-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All statuses</option><option value="open">Open</option><option value="investigating">Investigating</option><option value="recovering">Recovering</option><option value="resolved">Resolved</option></select></label><label><span>Service</span><select className="small-select" value={serviceFilter} onChange={(event) => setServiceFilter(event.target.value)}><option value="all">All services</option>{services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}</select></label><label><span>Date</span><select className="small-select" value={incidentRange} onChange={(event) => setIncidentRange(event.target.value)}><option value="all">All dates</option><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option></select></label></div><section className="dash-card panel"><IncidentTable incidents={matchingIncidents} /></section>{dialogLayer}{toastLayer}</>
  }

  if (page === 'recovery' || page === 'recoveries') {
    const pending = filteredRecoveries.filter((item) => item.status === 'pending_approval').length
    const approved = filteredRecoveries.filter((item) => item.status === 'approved').length
    const running = filteredRecoveries.filter((item) => item.status === 'running').length
    const completed = filteredRecoveries.filter((item) => item.status === 'completed').length
    const failed = filteredRecoveries.filter((item) => item.status === 'failed').length
    return <>{commonNotices}{heading('Recovery center', 'Review policy-gated operations and verify status returned by the backend.')}<div className="metric-grid metric-grid-five"><MetricCount label="Pending approval" value={String(pending).padStart(2, '0')} note="Requires review" icon={Clock3} /><MetricCount label="Approved" value={String(approved).padStart(2, '0')} note="Awaiting execution" icon={CheckCircle2} /><MetricCount label="Running" value={String(running).padStart(2, '0')} note="Backend-reported" icon={RefreshCw} /><MetricCount label="Completed" value={String(completed).padStart(2, '0')} note="Verification required" icon={ShieldCheck} /><MetricCount label="Failed" value={String(failed).padStart(2, '0')} note="Needs escalation" icon={ArrowDownRight} /></div><section className="dash-card panel" style={{ marginTop: 13 }}><div className="panel-header"><div><h2 className="panel-title">Recovery queue</h2><p className="panel-subtitle">Approval controls require a configured backend. Rejections are unavailable until the API contract adds that endpoint.</p></div></div><RecoveryTable actions={filteredRecoveries} allowControls onApprove={beginApproval} onReject={beginRejection} /></section>{dialogLayer}{toastLayer}</>
  }

  if (page === 'history') {
    const history = filteredRecoveries.filter((item) => item.status === 'completed' || item.status === 'failed')
    return <>{commonNotices}{heading('Recovery history', 'Review completed and failed actions, timing, result, and verification state.', <span className="demo-label">{history.length} records</span>)}<section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Recorded operations</h2><p className="panel-subtitle">An action is only successful when the backend confirms completion and verification.</p></div></div><RecoveryTable actions={history} /></section>{dialogLayer}{toastLayer}</>
  }

  if (page === 'monitoring') {
    return <>{commonNotices}<MonitoringView services={filteredServices} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'analytics') {
    return <>{commonNotices}<AnalyticsView analytics={analytics} demoMode={demoMode} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'reports') {
    return <>{commonNotices}<ReportsView incidents={filteredIncidents} demoMode={demoMode} onDownload={downloadReport} busyId={busyId} />{dialogLayer}{toastLayer}</>
  }

  if (page === 'settings') {
    return <>{commonNotices}<SettingsView demoMode={demoMode} healthStatus={healthResource.data?.status} />{dialogLayer}{toastLayer}</>
  }

  if (page !== 'overview') {
    return <>{commonNotices}{heading('Page not found', 'Choose a workspace area from the navigation.', <Link className="dash-button" href="/dashboard"><ArrowDownRight size={12} />Overview</Link>)}{dialogLayer}{toastLayer}</>
  }

  return <>{commonNotices}<OverviewView services={filteredServices} incidents={filteredIncidents} recoveries={filteredRecoveries} analytics={analytics} demoMode={demoMode} loading={loading} onRefresh={refreshData} />{dialogLayer}{toastLayer}</>
}
