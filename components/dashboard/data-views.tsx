'use client'

import { useMemo, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import Link from 'next/link'
import useSWR from 'swr'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, CheckCircle2, CircleAlert, Clock3, Cpu, Download, Gauge, MemoryStick, Server, ShieldCheck } from 'lucide-react'
import type { AnalyticsSummary, Incident, RecoveryAction, Service, ServiceMetrics } from '@/types'
import { servicesApi } from '@/lib/api/resources'
import { demoServices } from '@/lib/demo/mock-data'
import { isApiConfigured } from '@/lib/api/client'
import { IncidentAreaChart, AvailabilityChart } from '@/components/dashboard/charts'

const tooltipStyle = { background: '#111827', border: '1px solid rgba(148,163,184,.18)', borderRadius: 9, color: '#e2e8f0', fontSize: 10 }

function EmptyState({ title, detail }: { title: string; detail: string }) {
  return <div className="empty-state" role="status"><span className="empty-state-icon"><Activity size={15} /></span><strong>{title}</strong><p>{detail}</p></div>
}

function MetricCard({ label, value, detail, icon: Icon, tone = 'teal' }: { label: string; value: string; detail: string; icon: LucideIcon; tone?: 'teal' | 'violet' | 'amber' }) {
  return <article className="dash-card metric-card"><div className="metric-top"><span>{label}</span><span className={`metric-icon ${tone}`}><Icon size={14} /></span></div><strong className="metric-value">{value}</strong><div className="metric-foot"><span>{detail}</span><span className={tone === 'amber' ? 'metric-warning' : 'metric-good'}>●</span></div></article>
}

function ServiceStatus({ status }: { status: Service['status'] }) {
  return <span className={`status-chip ${status === 'healthy' ? 'completed' : status}`}>{status}</span>
}

export function OverviewView({ services, incidents, recoveries, analytics, demoMode, loading, onRefresh }: { services: Service[]; incidents: Incident[]; recoveries: RecoveryAction[]; analytics?: AnalyticsSummary; demoMode: boolean; loading: boolean; onRefresh: () => void }) {
  const [range, setRange] = useState('7d')
  const inRange = useMemo(() => incidents.filter((incident) => {
    if (range === 'all') return true
    const text = incident.detectedAt.toLowerCase()
    const timestamp = Date.parse(incident.detectedAt)
    const age = Date.now() - timestamp
    if (range === '24h') return text.includes('today') || (!Number.isNaN(timestamp) && age >= 0 && age <= 86_400_000)
    return text.includes('today') || text.includes('yesterday') || Number.isNaN(timestamp) || (age >= 0 && age <= 604_800_000)
  }), [incidents, range])
  const healthy = services.filter((item) => item.status === 'healthy').length
  const active = incidents.filter((item) => item.status !== 'resolved').length
  const recoveredToday = recoveries.filter((item) => item.status === 'completed' && item.requestedAt.toLowerCase().includes('today')).length
  return <>
    <div className="dashboard-heading"><div><h1>Infrastructure overview</h1><p>A clear view of service health, incident activity, and verified recovery.</p></div><div className="dashboard-toolbar"><span className={`demo-label ${demoMode ? '' : 'live'}`}><span className="status-dot" />{demoMode ? 'DEMO DATA' : 'LIVE API'}</span><label className="sr-only" htmlFor="overview-range">Incident time range</label><select id="overview-range" className="small-select" value={range} onChange={(event) => setRange(event.target.value)}><option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option><option value="all">All available</option></select><button className="dash-button" onClick={onRefresh}><Activity size={12} />Refresh data</button></div></div>
    {loading && <div className="notice-strip" role="status">Loading current data from the configured backend. No sample metrics are shown in live API mode.</div>}
    <div className="metric-grid metric-grid-six">
      <MetricCard label="Monitored services" value={demoMode || services.length ? String(services.length).padStart(2, '0') : '—'} detail="In selected environment" icon={Server} />
      <MetricCard label="Healthy services" value={demoMode || services.length ? String(healthy).padStart(2, '0') : '—'} detail={services.length ? `${Math.round((healthy / services.length) * 100)}% of monitored` : 'Awaiting live data'} icon={CheckCircle2} />
      <MetricCard label="Active incidents" value={demoMode || incidents.length ? String(active).padStart(2, '0') : '—'} detail="Not yet resolved" icon={CircleAlert} tone="amber" />
      <MetricCard label="Recoveries today" value={demoMode || recoveries.length ? String(recoveredToday).padStart(2, '0') : '—'} detail={demoMode ? 'Illustrative sample count' : 'Backend-confirmed completions'} icon={ShieldCheck} />
      <MetricCard label="Recovery success" value={analytics ? `${analytics.recoverySuccessRate}%` : '—'} detail={analytics ? 'Available analytics window' : 'Awaiting live data'} icon={ArrowUpRight} tone="violet" />
      <MetricCard label="Mean recovery" value={analytics ? `${analytics.recoveryDurationMinutes} min` : '—'} detail={analytics ? 'Available analytics window' : 'Awaiting live data'} icon={Clock3} />
    </div>
    <div className="dashboard-grid">
      <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Incident activity</h2><p className="panel-subtitle">{demoMode ? 'Illustrative activity · not live infrastructure' : 'Data returned by the configured API'}</p></div><Link className="text-link" href="/dashboard/analytics">View analytics <ArrowDownRight size={12} /></Link></div><div className="chart-wrap">{analytics?.history.length ? <IncidentAreaChart data={analytics.history} /> : <EmptyState title={loading ? 'Loading activity' : 'No analytics available'} detail="The backend has not supplied incident history for this period." />}</div></section>
      <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Service health</h2><p className="panel-subtitle">Availability and response health</p></div><Link className="text-link" href="/dashboard/services">All services <ArrowDownRight size={12} /></Link></div><div className="service-health-list">{services.length ? services.slice(0, 5).map((service) => <Link href={`/dashboard/services/${encodeURIComponent(service.id)}`} className="service-health-row" key={service.id}><span className={`status-dot ${service.status === 'healthy' ? '' : service.status}`} /><span className="service-health-main"><strong>{service.name}</strong><small>{service.environment} · {service.latencyMs} ms latency</small></span><ServiceStatus status={service.status} /></Link>) : <EmptyState title={loading ? 'Loading services' : 'No services reported'} detail="Services appear here when the backend returns monitored infrastructure." />}</div></section>
    </div>
    <div className="dashboard-grid">
      <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Recent incidents</h2><p className="panel-subtitle">{inRange.length} incidents in this view</p></div><Link className="text-link" href="/dashboard/incidents">View incidents <ArrowDownRight size={12} /></Link></div><IncidentTable incidents={inRange.slice(0, 5)} compact /></section>
      <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Recovery activity</h2><p className="panel-subtitle">Actions and verification status</p></div><Link className="text-link" href="/dashboard/history">View history <ArrowDownRight size={12} /></Link></div><RecoveryTimeline actions={recoveries.slice(0, 4)} /></section>
    </div>
  </>
}

export function ServiceTable({ services }: { services: Service[] }) {
  type SortKey = 'name' | 'environment' | 'status' | 'availability' | 'errorRate' | 'latencyMs' | 'lastChecked'
  const [sortKey, setSortKey] = useState<SortKey>('name')
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc')
  const columns: Array<{ label: string; key: SortKey }> = [
    { label: 'Service', key: 'name' }, { label: 'Environment', key: 'environment' }, { label: 'Health', key: 'status' },
    { label: 'Availability', key: 'availability' }, { label: 'Error rate', key: 'errorRate' }, { label: 'Latency', key: 'latencyMs' }, { label: 'Last checked', key: 'lastChecked' },
  ]
  const sorted = [...services].sort((first, second) => {
    const a = first[sortKey]
    const b = second[sortKey]
    const comparison = typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b))
    return direction === 'asc' ? comparison : -comparison
  })
  function setSort(key: SortKey) {
    if (sortKey === key) setDirection(direction === 'asc' ? 'desc' : 'asc')
    else { setSortKey(key); setDirection('asc') }
  }
  if (!sorted.length) return <EmptyState title="No services found" detail="Try changing the environment or search terms." />
  return <div className="data-table-wrap"><table className="data-table"><thead><tr>{columns.map((column) => <th key={column.key} aria-sort={sortKey === column.key ? direction === 'asc' ? 'ascending' : 'descending' : 'none'}><button className="table-sort" onClick={() => setSort(column.key)}>{column.label}{sortKey === column.key && <span aria-hidden="true">{direction === 'asc' ? ' ↑' : ' ↓'}</span>}</button></th>)}</tr></thead><tbody>{sorted.map((service) => <tr key={service.id}><td><Link className="table-primary-link" href={`/dashboard/services/${encodeURIComponent(service.id)}`}>{service.name}</Link><small className="table-subtext">{service.id}</small></td><td>{service.environment}</td><td><ServiceStatus status={service.status} /></td><td>{service.availability.toFixed(2)}%</td><td>{service.errorRate.toFixed(2)}%</td><td>{service.latencyMs} ms</td><td>{service.lastChecked}</td></tr>)}</tbody></table></div>
}

export function IncidentTable({ incidents, compact = false }: { incidents: Incident[]; compact?: boolean }) {
  if (!incidents.length) return <EmptyState title="No incidents found" detail="Adjust the filters or connect incident data from the backend." />
  return <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Incident</th><th>Service</th><th>Severity</th><th>Status</th><th>Detected</th>{!compact && <th>Recovery</th>}</tr></thead><tbody>{incidents.map((incident) => <tr key={incident.id}><td><Link className="table-primary-link" href={`/dashboard/incidents/${encodeURIComponent(incident.id)}`}>{incident.id}</Link><small className="table-subtext">{incident.title}</small></td><td>{incident.serviceName}</td><td><span className={`status-chip ${incident.severity === 'critical' || incident.severity === 'high' ? 'critical' : incident.severity === 'medium' ? 'degraded' : 'completed'}`}>{incident.severity}</span></td><td><span className={`status-chip ${incident.status === 'resolved' ? 'completed' : incident.status === 'open' ? 'critical' : 'pending'}`}>{incident.status.replace('_', ' ')}</span></td><td>{incident.detectedAt}</td>{!compact && <td>{incident.recoveryStatus}</td>}</tr>)}</tbody></table></div>
}

export function RecoveryTable({ actions, onApprove, onReject, allowControls = false }: { actions: RecoveryAction[]; onApprove?: (id: string) => void; onReject?: (id: string) => void; allowControls?: boolean }) {
  if (!actions.length) return <EmptyState title="No recovery actions" detail="Recovery activity will appear here when returned by the configured backend." />
  return <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Action</th><th>Incident</th><th>Requested by</th><th>Status</th><th>Verification</th><th>Duration</th>{allowControls && <th>Controls</th>}</tr></thead><tbody>{actions.map((action) => <tr key={action.id}><td><strong>{action.action}</strong><small className="table-subtext">{action.serviceName} · {action.requestedAt}</small></td><td><Link className="table-primary-link" href={`/dashboard/incidents/${encodeURIComponent(action.incidentId)}`}>{action.incidentId}</Link></td><td>{action.requestedBy}</td><td><span className={`status-chip ${action.status === 'completed' ? 'completed' : action.status === 'failed' ? 'failed' : action.status === 'running' ? 'degraded' : 'pending'}`}>{action.status.replace('_', ' ')}</span></td><td><span className={`status-chip ${action.verification === 'passed' ? 'completed' : action.verification === 'failed' ? 'failed' : 'pending'}`}>{action.verification}</span></td><td>{action.durationSeconds === undefined ? '—' : `${action.durationSeconds}s`}</td>{allowControls && <td>{action.status === 'pending_approval' ? <div className="row-actions"><button className="dash-button primary" onClick={() => onApprove?.(action.id)}>Approve</button><button className="dash-button danger" onClick={() => onReject?.(action.id)}>Reject</button></div> : <span className="table-subtext">No action required</span>}</td>}</tr>)}</tbody></table></div>
}

export function RecoveryTimeline({ actions }: { actions: RecoveryAction[] }) {
  if (!actions.length) return <EmptyState title="No recovery activity" detail="Actions are recorded after the backend confirms a recovery workflow." />
  return <div className="activity-list">{actions.map((action) => <div className="activity-item" key={action.id}><span className="activity-bullet"><ShieldCheck size={11} /></span><div className="activity-text"><strong>{action.action}</strong><div>{action.serviceName} · {action.status.replace('_', ' ')}</div><small>{action.requestedAt} · verification {action.verification}</small></div></div>)}</div>
}

function demoMetrics(serviceId: string): ServiceMetrics | undefined {
  const service = demoServices.find((item) => item.id === serviceId)
  if (!service) return undefined
  const healthy = service.status === 'healthy'
  return {
    serviceId,
    sampledAt: service.lastChecked,
    cpuPercent: healthy ? 32 : 76,
    memoryPercent: healthy ? 58 : 81,
    requestRate: healthy ? 1240 : 980,
    errorRate: service.errorRate,
    latencyMs: service.latencyMs,
    availability: service.availability,
    history: [{ time: '00:00', value: 38 }, { time: '04:00', value: 42 }, { time: '08:00', value: healthy ? 34 : 71 }, { time: '12:00', value: healthy ? 47 : 63 }, { time: '16:00', value: healthy ? 40 : 78 }, { time: '20:00', value: healthy ? 36 : 59 }],
  }
}

function ServiceMetricsPanel({ service }: { service: Service }) {
  const demoMode = !isApiConfigured
  const sampleMetrics = demoMode ? demoMetrics(service.id) : undefined
  const metricKey = demoMode ? sampleMetrics ? ['demo-service-metrics', service.id] : null : ['service-metrics', service.id]
  const metricResource = useSWR<ServiceMetrics>(metricKey, () => demoMode ? Promise.resolve(sampleMetrics as ServiceMetrics) : servicesApi.metrics(service.id), { fallbackData: sampleMetrics, revalidateOnFocus: false })
  const metrics = metricResource.data
  const loading = isApiConfigured && metricResource.isLoading
  return <>
    {loading && <div className="notice-strip" role="status">Loading backend-supplied metrics for {service.name}. No sample values are shown.</div>}
    {metricResource.error && <div className="error-strip" role="alert">Could not load metrics: {metricResource.error.message}</div>}
    {demoMode && <div className="notice-strip">Illustrative demo metrics only. This service is not connected to infrastructure.</div>}
    <div className="metric-grid metric-grid-six">
      <MetricCard label="CPU utilization" value={metrics ? `${metrics.cpuPercent}%` : '—'} detail="Latest sample" icon={Cpu} />
      <MetricCard label="Memory usage" value={metrics ? `${metrics.memoryPercent}%` : '—'} detail="Latest sample" icon={MemoryStick} tone="violet" />
      <MetricCard label="Request rate" value={metrics ? `${metrics.requestRate}/min` : '—'} detail="Requests per minute" icon={Activity} />
      <MetricCard label="Error rate" value={metrics ? `${metrics.errorRate}%` : '—'} detail="Current window" icon={CircleAlert} tone="amber" />
      <MetricCard label="Latency" value={metrics ? `${metrics.latencyMs} ms` : '—'} detail="Response time" icon={Gauge} />
      <MetricCard label="Availability" value={metrics ? `${metrics.availability}%` : '—'} detail="Reported uptime" icon={CheckCircle2} />
    </div>
    <section className="dash-card panel" style={{ marginTop: 13 }}><div className="panel-header"><div><h2 className="panel-title">Service performance</h2><p className="panel-subtitle">{metrics ? `Sampled ${metrics.sampledAt}` : 'Waiting for a backend metrics response'}</p></div><span className={`demo-label ${demoMode ? '' : 'live'}`}>{demoMode ? 'DEMO DATA' : 'API DATA'}</span></div><div className="chart-wrap">{metrics?.history.length ? <ResponsiveContainer width="100%" height="100%"><AreaChart data={metrics.history} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}><defs><linearGradient id="serviceFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#35d6c5" stopOpacity={.22} /><stop offset="100%" stopColor="#35d6c5" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="rgba(148,163,184,.1)" vertical={false} /><XAxis dataKey="time" tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} /><YAxis tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={tooltipStyle} /><Area dataKey="value" name="Metric value" type="monotone" stroke="#35d6c5" strokeWidth={2} fill="url(#serviceFill)" /></AreaChart></ResponsiveContainer> : <EmptyState title={loading ? 'Loading metrics' : 'Metrics unavailable'} detail="The configured backend has not supplied a history series for this service." />}</div></section>
  </>
}

export function ServiceDetailView({ service, incidents, recoveries }: { service: Service; incidents: Incident[]; recoveries: RecoveryAction[] }) {
  const serviceIncidents = incidents.filter((item) => item.serviceId === service.id)
  const serviceRecoveries = recoveries.filter((item) => item.serviceName === service.name)
  return <>
    <ServiceMetricsPanel service={service} />
    <div className="dashboard-grid">
      <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Recent incidents</h2><p className="panel-subtitle">Incidents associated with {service.name}</p></div></div><IncidentTable incidents={serviceIncidents} compact /></section>
      <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Recovery actions</h2><p className="panel-subtitle">Actions linked to this service</p></div></div><RecoveryTimeline actions={serviceRecoveries} /></section>
    </div>
  </>
}

export function IncidentDetailView({ incident, onRequestRecovery }: { incident: Incident; onRequestRecovery: () => void }) {
  return <>
    <div className="incident-detail-grid">
      <div className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Incident evidence</h2><p className="panel-subtitle">Signals correlated with this incident</p></div></div><div className="evidence-list">{incident.evidence.length ? incident.evidence.map((item) => <div className="evidence-row" key={item.id}><span className="activity-bullet"><Activity size={11} /></span><div><strong>{item.title}</strong><p>{item.detail}</p><small>{item.kind} · {item.timestamp}</small></div></div>) : <EmptyState title="No evidence attached" detail="The backend has not supplied evidence for this incident." />}</div></div>
      <div className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Diagnosis</h2><p className="panel-subtitle">Evidence-led incident summary</p></div></div><div className="evidence-row"><CircleAlert size={14} /><div><strong>Probable cause</strong><p>{incident.probableCause}</p></div></div><div className="evidence-row"><ArrowUpRight size={14} /><div><strong>Recommended action</strong><p>{incident.recommendedAction}</p></div></div><div className="incident-values"><div><small>Error rate</small><strong>{incident.errorRate}%</strong></div><div><small>Threshold</small><strong>{incident.threshold}%</strong></div></div><button className="dash-button primary" onClick={onRequestRecovery}>Request controlled recovery</button></div>
    </div>
    <section className="dash-card panel" style={{ marginTop: 13 }}><div className="panel-header"><div><h2 className="panel-title">Incident timeline</h2><p className="panel-subtitle">Recorded events · {incident.detectedAt}</p></div><span className="status-chip">{incident.recoveryStatus}</span></div><div className="activity-list">{incident.events.length ? incident.events.map((event) => <div className="activity-item" key={event.id}><span className={`activity-bullet ${event.tone}`}><Clock3 size={11} /></span><div className="activity-text"><strong>{event.label}</strong><div>{event.detail}</div><small>{event.timestamp}</small></div></div>) : <EmptyState title="No timeline events" detail="Events will appear here when returned by the backend." />}</div></section>
  </>
}

export function MonitoringView({ services }: { services: Service[] }) {
  const [selectedId, setSelectedId] = useState('')
  const selected = services.find((service) => service.id === selectedId) ?? services[0]
  return <>
    <div className="dashboard-heading"><div><h1>Infrastructure monitoring</h1><p>Operational metrics supplied by the configured backend or labeled demo data.</p></div><div className="dashboard-toolbar"><label className="sr-only" htmlFor="monitoring-service">Service</label><select id="monitoring-service" className="small-select" value={selected?.id ?? ''} onChange={(event) => setSelectedId(event.target.value)}><option value="" disabled>Select a service</option>{services.map((service) => <option key={service.id} value={service.id}>{service.name}</option>)}</select></div></div>
    {selected ? <ServiceMetricsPanel service={selected} /> : <EmptyState title="No monitored services" detail="Infrastructure metrics will appear after the backend supplies service data." />}
  </>
}

export function AnalyticsView({ analytics, demoMode }: { analytics?: AnalyticsSummary; demoMode: boolean }) {
  const [range, setRange] = useState('all')
  const rows = analytics?.history ?? []
  const visible = range === '7' ? rows.slice(-7) : range === '30' ? rows.slice(-30) : rows
  function exportCsv() {
    if (!visible.length) return
    const csvCell = (value: string | number) => {
      const text = String(value)
      const safe = /^[=+@-]/.test(text) ? `'${text}` : text
      return `"${safe.replaceAll('"', '""')}"`
    }
    const csv = [
      ['date', 'incidents', 'recoveries', 'availability'].map(csvCell).join(','),
      ...visible.map((row) => [row.date, row.incidents, row.recoveries, row.availability].map(csvCell).join(',')),
    ].join('\n')
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `autoheal-analytics-${demoMode ? 'demo-' : ''}${new Date().toISOString().slice(0, 10)}.csv`
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <>
    <div className="dashboard-heading"><div><h1>Analytics</h1><p>Understand detection, recovery, and service reliability trends.</p></div><div className="dashboard-toolbar"><label className="sr-only" htmlFor="analytics-range">Data range</label><select id="analytics-range" className="small-select" value={range} onChange={(event) => setRange(event.target.value)}><option value="all">All available data</option><option value="7">Last 7 points</option><option value="30">Last 30 points</option></select><button className="dash-button" onClick={exportCsv} disabled={!visible.length}><Download size={12} />Export CSV</button></div></div>
    {demoMode && <div className="notice-strip">Illustrative analytics only. The included series is sample data and is not a customer result.</div>}
    <div className="metric-grid metric-grid-four"><MetricCard label="Detection latency" value={analytics ? `${analytics.detectionLatencySeconds}s` : '—'} detail="Average time to detect" icon={Gauge} /><MetricCard label="Mean recovery" value={analytics ? `${analytics.recoveryDurationMinutes} min` : '—'} detail="Reported recovery duration" icon={Clock3} tone="violet" /><MetricCard label="Recovery success" value={analytics ? `${analytics.recoverySuccessRate}%` : '—'} detail="Verified outcomes" icon={CheckCircle2} /><MetricCard label="False-positive rate" value={analytics ? `${analytics.falsePositiveRate}%` : '—'} detail="Reported by backend" icon={CircleAlert} tone="amber" /></div>
    <div className="dashboard-grid equal"><section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Incident and recovery trend</h2><p className="panel-subtitle">{demoMode ? 'Illustrative series' : 'Backend-supplied series'}</p></div></div><div className="chart-wrap">{visible.length ? <IncidentAreaChart data={visible} /> : <EmptyState title="Analytics unavailable" detail="No history series was returned for this range." />}</div></section><section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Availability trend</h2><p className="panel-subtitle">Service reliability across the selected window</p></div></div><div className="chart-wrap">{visible.length ? <AvailabilityChart data={visible} /> : <EmptyState title="Availability unavailable" detail="No availability series was returned by the backend." />}</div></section></div>
    <section className="dash-card panel" style={{ marginTop: 13 }}><div className="panel-header"><div><h2 className="panel-title">Incident frequency and recovery</h2><p className="panel-subtitle">{analytics ? `${analytics.incidentCount} total incidents in the available window` : 'Waiting for analytics data'}</p></div></div><div className="data-table-wrap"><table className="data-table"><thead><tr><th>Period</th><th>Incidents</th><th>Recoveries</th><th>Availability</th></tr></thead><tbody>{visible.map((row) => <tr key={row.date}><td>{row.date}</td><td>{row.incidents}</td><td>{row.recoveries}</td><td>{row.availability}%</td></tr>)}</tbody></table></div></section>
  </>
}

export function ReportsView({ incidents, demoMode, onDownload, busyId }: { incidents: Incident[]; demoMode: boolean; onDownload: (id: string) => void; busyId?: string }) {
  return <>
    <div className="dashboard-heading"><div><h1>Reports</h1><p>Generate incident reports from backend data and download the returned file.</p></div><span className={`demo-label ${demoMode ? '' : 'live'}`}>{demoMode ? 'BACKEND REQUIRED' : 'API CONNECTED'}</span></div>
    {demoMode && <div className="notice-strip">No report files are generated from sample data. Configure the FastAPI backend to enable incident report downloads.</div>}
    <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Incident reports</h2><p className="panel-subtitle">{incidents.length} available incident records</p></div></div>{incidents.length ? <div className="data-table-wrap"><table className="data-table"><thead><tr><th>Incident</th><th>Service</th><th>Severity</th><th>Detected</th><th>Report</th></tr></thead><tbody>{incidents.map((incident) => <tr key={incident.id}><td><Link className="table-primary-link" href={`/dashboard/incidents/${encodeURIComponent(incident.id)}`}>{incident.id}</Link><small className="table-subtext">{incident.title}</small></td><td>{incident.serviceName}</td><td>{incident.severity}</td><td>{incident.detectedAt}</td><td><button className="dash-button" disabled={demoMode || busyId === incident.id} onClick={() => onDownload(incident.id)}><Download size={12} />{busyId === incident.id ? 'Preparing…' : 'Download report'}</button></td></tr>)}</tbody></table></div> : <EmptyState title="No incident reports" detail="Reports will appear when the backend returns incident records." />}</section>
  </>
}

export function SettingsView({ demoMode, healthStatus }: { demoMode: boolean; healthStatus?: string }) {
  const items = [
    { title: 'Account and profile', detail: 'User identity and preferences are managed by the authentication backend.' },
    { title: 'Notification preferences', detail: 'Notification channels and alert routing are not yet part of the API contract.' },
    { title: 'Recovery policies', detail: 'Allowlisted actions, retry limits, and cooldowns are configured server-side.' },
    { title: 'Approval controls', detail: 'Sensitive recovery operations require backend policy validation.' },
    { title: 'Environment configuration', detail: 'The selected environment filter applies to the current workspace view.' },
    { title: 'Security preferences', detail: 'Credentials are never requested or stored by this frontend preview.' },
  ]
  return <>
    <div className="dashboard-heading"><div><h1>Workspace settings</h1><p>Review the frontend connection and backend-managed governance boundaries.</p></div><span className={`demo-label ${demoMode ? '' : 'live'}`}>{demoMode ? 'DEMO MODE' : 'API MODE'}</span></div>
    <section className="dash-card panel"><div className="panel-header"><div><h2 className="panel-title">Backend connection</h2><p className="panel-subtitle">Connection state is derived from the frontend API configuration.</p></div><span className={`status-chip ${demoMode ? 'pending' : healthStatus === 'healthy' || healthStatus === 'ok' ? 'completed' : 'degraded'}`}>{demoMode ? 'Not configured' : healthStatus ?? 'Checking health'}</span></div><div className="settings-connection"><span className="settings-connection-icon"><Server size={17} /></span><div><strong>{demoMode ? 'FastAPI endpoint not configured' : 'FastAPI endpoint configured'}</strong><p>{demoMode ? 'Set NEXT_PUBLIC_API_BASE_URL to connect the API. The demo provider remains read-only.' : healthStatus ? `Backend health response: ${healthStatus}. Authentication and CORS remain backend responsibilities.` : 'The backend health endpoint has not returned a status yet. Authentication and CORS remain backend responsibilities.'}</p></div></div></section>
    <div className="settings-grid">{items.map((item) => <section className="dash-card settings-card" key={item.title}><span className="settings-icon"><ShieldCheck size={14} /></span><div><h2>{item.title}</h2><p>{item.detail}</p><span className="settings-managed">Backend managed</span></div></section>)}</div>
  </>
}
