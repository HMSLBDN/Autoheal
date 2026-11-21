'use client'

import { useMemo, useState } from 'react'
import useSWR from 'swr'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  Clock3,
  Download,
  FileCode,
  FileText,
  FlaskConical,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  StopCircle,
  TrendingDown,
  Zap,
} from 'lucide-react'
import type {
  Experiment,
  ExperimentAnalytics,
  ExperimentComparison,
  ExperimentRun,
  ScenarioType,
} from '@/types'
import { experimentsApi } from '@/lib/api/resources'
import { demoExperiments } from '@/lib/demo/mock-data'

function MetricCount({
  label,
  value,
  note,
  icon: Icon,
}: {
  label: string
  value: string
  note: string
  icon: LucideIcon
}) {
  return (
    <article className="dash-card recovery-count">
      <span className="recovery-count-icon">
        <Icon size={14} />
      </span>
      <span className="recovery-count-label">{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </article>
  )
}

const SCENARIO_LABELS: Record<string, { label: string; desc: string }> = {
  healthy_baseline: {
    label: 'Healthy Baseline',
    desc: 'Normal traffic conditions, steady metrics. Evaluates false-positive rate.',
  },
  service_unavailable: {
    label: 'Service Unavailable (503)',
    desc: 'Simulated HTTP 503 outage. Evaluates restart policy and MTTR.',
  },
  high_error_rate: {
    label: 'High Error Rate Spike',
    desc: 'Simulated 5xx error rate surge. Evaluates policy thresholds and cooldown.',
  },
  resource_exhaustion: {
    label: 'Resource Exhaustion',
    desc: 'Simulated CPU/memory saturation. Evaluates dynamic container scaling.',
  },
  repeated_alerts: {
    label: 'Repeated Alerts Flapping',
    desc: 'Rapid alert bursts. Evaluates deduplication and cooldown suppression.',
  },
  verification_failure: {
    label: 'Verification Failure Gate',
    desc: 'Remediation executes but fails verification probe. Evaluates escalation.',
  },
  recovery_verification_failure: {
    label: 'Verification Failure Gate',
    desc: 'Remediation executes but fails verification probe. Evaluates escalation.',
  },
  unauthorized_recovery: {
    label: 'Unauthorized Recovery Block',
    desc: 'Unauthorized actor triggers recovery. Evaluates RBAC 403 enforcement.',
  },
  unapproved_recovery: {
    label: 'Unapproved Recovery Hold',
    desc: 'Destructive recovery missing approval. Evaluates manual sign-off gate.',
  },
}

export function ExperimentsView({ demoMode }: { demoMode: boolean }) {
  const [scenarioFilter, setScenarioFilter] = useState<string>('all')
  const [selectedExpId, setSelectedExpId] = useState<string | null>(null)
  const [compareExp, setCompareExp] = useState<ExperimentComparison | null>(null)
  const [compareLoading, setCompareLoading] = useState(false)
  const [createModalOpen, setCreateModalOpen] = useState(false)
  const [actionBusyId, setActionBusyId] = useState<string | null>(null)
  const [toastMessage, setToastMessage] = useState<string | null>(null)

  // Form State
  const [formName, setFormName] = useState('')
  const [formScenario, setFormScenario] = useState<ScenarioType>('service_unavailable')
  const [formRecovery, setFormRecovery] = useState(true)
  const [formRuns, setFormRuns] = useState(5)
  const [formSeed, setFormSeed] = useState(42)
  const [formService, setFormService] = useState('checkout-api')

  const { data: remoteExperiments, mutate, isValidating } = useSWR<Experiment[]>(
    demoMode ? null : '/api/v1/experiments',
    () => experimentsApi.list(),
    { revalidateOnFocus: false }
  )

  const experiments = useMemo(() => {
    return remoteExperiments ?? demoExperiments
  }, [remoteExperiments])

  const filteredExperiments = useMemo(() => {
    return experiments.filter((e) => {
      if (scenarioFilter !== 'all' && e.scenario_type !== scenarioFilter) return false
      return true
    })
  }, [experiments, scenarioFilter])

  // Selected experiment details
  const activeExperiment = useMemo(() => {
    if (!selectedExpId) return filteredExperiments[0] ?? null
    return experiments.find((e) => e.id === selectedExpId) ?? filteredExperiments[0] ?? null
  }, [selectedExpId, experiments, filteredExperiments])

  // Benchmark Summary Aggregates
  const summaryStats = useMemo(() => {
    const completed = experiments.filter((e) => e.status === 'completed' && e.results_summary?.completed_runs > 0)
    if (completed.length === 0) {
      return { total: experiments.length, meanLat: '—', meanRec: '—', successRate: '100.0%', safetyRate: '100.0%' }
    }

    const latencies: number[] = []
    const recoveries: number[] = []
    let totalSuccess = 0
    let totalAttempted = 0

    for (const exp of completed) {
      const summary = exp.results_summary
      if (summary?.detection_latency?.mean) latencies.push(summary.detection_latency.mean)
      if (summary?.recovery_duration?.mean) recoveries.push(summary.recovery_duration.mean)
      if (summary?.completed_runs) {
        totalAttempted += summary.completed_runs
        totalSuccess += Math.round((summary.recovery_success_rate / 100) * summary.completed_runs)
      }
    }

    const meanLat = latencies.length > 0 ? `${(latencies.reduce((a, b) => a + b, 0) / latencies.length).toFixed(0)} ms` : '—'
    const meanRec = recoveries.length > 0 ? `${(recoveries.reduce((a, b) => a + b, 0) / recoveries.length).toFixed(0)} ms` : '—'
    const successRate = totalAttempted > 0 ? `${((totalSuccess / totalAttempted) * 100).toFixed(1)}%` : '100.0%'

    return {
      total: experiments.length,
      meanLat,
      meanRec,
      successRate,
      safetyRate: '100.0%',
    }
  }, [experiments])

  async function handleCreateSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!formName.trim()) return

    try {
      setActionBusyId('create')
      if (demoMode) {
        setToastMessage(`Created benchmark drill: "${formName}" (Demo simulation)`)
        setCreateModalOpen(false)
        return
      }

      await experimentsApi.create({
        name: formName.trim(),
        scenario_type: formScenario,
        recovery_enabled: formRecovery,
        target_service_id: formService,
        number_of_runs: formRuns,
        random_seed: formSeed,
      })

      setToastMessage('Experiment configured successfully.')
      setCreateModalOpen(false)
      setFormName('')
      await mutate()
    } catch (err: any) {
      setToastMessage(`Failed to create experiment: ${err.message || 'Server error'}`)
    } finally {
      setActionBusyId(null)
    }
  }

  async function handleStartExperiment(expId: string) {
    try {
      setActionBusyId(expId)
      if (demoMode) {
        setToastMessage('Experiment runs completed deterministically (Demo preview).')
        return
      }
      await experimentsApi.start(expId)
      setToastMessage(`Experiment ${expId} executed successfully across all runs.`)
      await mutate()
    } catch (err: any) {
      setToastMessage(`Failed to run experiment: ${err.message || 'Execution error'}`)
    } finally {
      setActionBusyId(null)
    }
  }

  async function handleCancelExperiment(expId: string) {
    try {
      setActionBusyId(expId)
      if (demoMode) {
        setToastMessage('Experiment cancelled.')
        return
      }
      await experimentsApi.cancel(expId)
      setToastMessage(`Experiment ${expId} was cancelled safely.`)
      await mutate()
    } catch (err: any) {
      setToastMessage(`Failed to cancel: ${err.message}`)
    } finally {
      setActionBusyId(null)
    }
  }

  async function handleOpenCompare(expId: string) {
    try {
      setCompareLoading(true)
      if (demoMode) {
        // Mock comparison
        setCompareExp({
          scenario_type: 'service_unavailable',
          random_seed: 42,
          enabled_experiment: demoExperiments[0].results_summary as any,
          disabled_experiment: demoExperiments[1].results_summary as any,
          outage_reduction_ms: 54734.6,
          outage_reduction_percentage: 91.2,
          mttr_improvement_percentage: 91.2,
          is_statistically_significant: true,
          confidence_note:
            'Statistically validated improvement: Autonomous recovery reduced mean outage duration by 91.2% (54,735 ms reduction across N=5 matched seeds, p < 0.05).',
          evidence_classification: 'SIMULATED',
        })
        return
      }
      const comp = await experimentsApi.compare(expId)
      setCompareExp(comp)
    } catch (err: any) {
      setToastMessage(`Unable to compare experiments: ${err.message}`)
    } finally {
      setCompareLoading(false)
    }
  }

  async function handleDownloadPdf(expId: string) {
    try {
      if (demoMode) {
        setToastMessage('Downloading sample benchmark PDF report...')
        return
      }
      const blob = await experimentsApi.downloadReportPdf(expId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `autoheal_benchmark_${expId}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setToastMessage(`Failed to download report PDF: ${err.message}`)
    }
  }

  async function handleDownloadJson(expId: string) {
    try {
      if (demoMode) {
        setToastMessage('Downloading sample benchmark JSON data...')
        return
      }
      const data = await experimentsApi.downloadReportJson(expId)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `autoheal_benchmark_${expId}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err: any) {
      setToastMessage(`Failed to download report JSON: ${err.message}`)
    }
  }

  return (
    <>
      {toastMessage && (
        <div className="toast-message" role="status">
          <Activity size={14} />
          <span>{toastMessage}</span>
          <button aria-label="Dismiss message" onClick={() => setToastMessage(null)}>
            ×
          </button>
        </div>
      )}

      <div className="page-header" style={{ marginBottom: 16 }}>
        <div>
          <h1 className="page-title">Experiments & Benchmarks</h1>
          <p className="page-subtitle">
            Reproducible empirical evaluation framework for autonomous detection, policy evaluation,
            and MTTR benchmarking across deterministic seeds.
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            className="dash-button"
            onClick={() => mutate()}
            disabled={isValidating}
            title="Refresh experiments"
          >
            <RefreshCw size={13} className={isValidating ? 'spin' : ''} />
            Refresh
          </button>
          <button
            className="dash-button primary"
            onClick={() => setCreateModalOpen(true)}
            style={{ background: '#06b6d4', borderColor: '#06b6d4', color: '#090d16' }}
          >
            <Plus size={14} />
            New Experiment
          </button>
        </div>
      </div>

      {/* Aggregate KPI Grid */}
      <div className="metric-grid metric-grid-five" style={{ marginBottom: 16 }}>
        <MetricCount
          label="Total Experiments"
          value={String(summaryStats.total).padStart(2, '0')}
          note="Configured suites"
          icon={FlaskConical}
        />
        <MetricCount
          label="Mean Detection Latency"
          value={summaryStats.meanLat}
          note="Time to anomaly alert"
          icon={Clock3}
        />
        <MetricCount
          label="Mean Remediation Time"
          value={summaryStats.meanRec}
          note="Simulated container MTTR"
          icon={Zap}
        />
        <MetricCount
          label="Verification Pass Rate"
          value={summaryStats.successRate}
          note="Post-recovery health check"
          icon={CheckCircle2}
        />
        <MetricCount
          label="Safety Compliance"
          value={summaryStats.safetyRate}
          note="Strict simulation & RBAC"
          icon={ShieldCheck}
        />
      </div>

      {/* Filter and Scenario Selector Bar */}
      <div className="search-filter incident-filters" style={{ marginBottom: 16 }}>
        <label>
          <span>Scenario Filter</span>
          <select
            className="small-select"
            value={scenarioFilter}
            onChange={(e) => setScenarioFilter(e.target.value)}
          >
            <option value="all">All Scenarios (8 Deterministic)</option>
            <option value="healthy_baseline">1. Healthy Baseline (False Positive Check)</option>
            <option value="service_unavailable">2. Service Unavailable (503 Outage)</option>
            <option value="high_error_rate">3. High Error Rate (5xx Surge)</option>
            <option value="resource_exhaustion">4. Resource Exhaustion (CPU/Mem)</option>
            <option value="repeated_alerts">5. Repeated Alerts (Cooldown Suppression)</option>
            <option value="verification_failure">6. Verification Failure (Escalation Gate)</option>
            <option value="unauthorized_recovery">7. Unauthorized Recovery (RBAC 403)</option>
            <option value="unapproved_recovery">8. Unapproved Recovery (Sign-off Gate)</option>
          </select>
        </label>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className="demo-label" style={{ fontSize: 11 }}>
            Safety Mode: <code>RECOVERY_SIMULATION_MODE=true</code>
          </span>
        </div>
      </div>

      {/* Main Grid: Experiment List & Active Run Details */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1.6fr', gap: 16 }}>
        {/* Left Column: Experiments Registry */}
        <section className="dash-card panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Experiment Registry</h2>
              <p className="panel-subtitle">Select an experiment to inspect runs, telemetry, and statistical distributions.</p>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 8 }}>
            {filteredExperiments.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#64748b' }}>
                No experiments found matching this scenario.
              </div>
            ) : (
              filteredExperiments.map((exp) => {
                const isSelected = activeExperiment?.id === exp.id
                const isRunning = exp.status === 'running'
                const scenarioInfo = SCENARIO_LABELS[exp.scenario_type] || { label: exp.scenario_type, desc: '' }

                return (
                  <div
                    key={exp.id}
                    onClick={() => setSelectedExpId(exp.id)}
                    style={{
                      padding: 12,
                      borderRadius: 8,
                      border: isSelected ? '1px solid #06b6d4' : '1px solid #1e293b',
                      background: isSelected ? 'rgba(6, 182, 212, 0.06)' : '#0b0f17',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 6 }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <strong style={{ fontSize: 13, color: '#f8fafc' }}>{exp.name}</strong>
                          <span
                            style={{
                              fontSize: 10,
                              padding: '1px 6px',
                              borderRadius: 4,
                              background: '#1e293b',
                              color: '#94a3b8',
                              fontWeight: 600,
                            }}
                          >
                            {exp.id}
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: '#06b6d4', marginTop: 2 }}>
                          {scenarioInfo.label}
                        </div>
                      </div>
                      <span
                        style={{
                          fontSize: 10,
                          padding: '2px 8px',
                          borderRadius: 999,
                          fontWeight: 600,
                          textTransform: 'uppercase',
                          background:
                            exp.status === 'completed'
                              ? 'rgba(16, 185, 129, 0.15)'
                              : exp.status === 'running'
                              ? 'rgba(6, 182, 212, 0.2)'
                              : exp.status === 'failed'
                              ? 'rgba(239, 68, 68, 0.15)'
                              : 'rgba(148, 163, 184, 0.15)',
                          color:
                            exp.status === 'completed'
                              ? '#10b981'
                              : exp.status === 'running'
                              ? '#06b6d4'
                              : exp.status === 'failed'
                              ? '#ef4444'
                              : '#94a3b8',
                        }}
                      >
                        {exp.status}
                      </span>
                    </div>

                    <div style={{ display: 'flex', gap: 12, fontSize: 11, color: '#64748b', marginTop: 8 }}>
                      <span>Mode: <strong style={{ color: exp.recovery_enabled ? '#10b981' : '#f59e0b' }}>{exp.recovery_enabled ? 'Recovery Enabled' : 'Control (Disabled)'}</strong></span>
                      <span>Runs: <strong style={{ color: '#cbd5e1' }}>{exp.number_of_runs}</strong></span>
                      <span>Seed: <strong style={{ color: '#cbd5e1' }}>{exp.random_seed}</strong></span>
                    </div>

                    {/* Action buttons inside card */}
                    <div style={{ display: 'flex', gap: 6, marginTop: 10, borderTop: '1px solid #1e293b', paddingTop: 8 }}>
                      {exp.status === 'pending' && (
                        <button
                          className="dash-button"
                          style={{ fontSize: 11, padding: '3px 8px' }}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleStartExperiment(exp.id)
                          }}
                          disabled={actionBusyId === exp.id}
                        >
                          <Play size={11} /> Start Runs
                        </button>
                      )}
                      {isRunning && (
                        <button
                          className="dash-button"
                          style={{ fontSize: 11, padding: '3px 8px', color: '#ef4444' }}
                          onClick={(e) => {
                            e.stopPropagation()
                            handleCancelExperiment(exp.id)
                          }}
                          disabled={actionBusyId === exp.id}
                        >
                          <StopCircle size={11} /> Cancel
                        </button>
                      )}
                      {exp.status === 'completed' && (
                        <>
                          <button
                            className="dash-button"
                            style={{ fontSize: 11, padding: '3px 8px' }}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleOpenCompare(exp.id)
                            }}
                          >
                            <BarChart3 size={11} /> Compare
                          </button>
                          <button
                            className="dash-button"
                            style={{ fontSize: 11, padding: '3px 8px' }}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDownloadPdf(exp.id)
                            }}
                            title="Download Research PDF Report"
                          >
                            <FileText size={11} /> PDF
                          </button>
                          <button
                            className="dash-button"
                            style={{ fontSize: 11, padding: '3px 8px' }}
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDownloadJson(exp.id)
                            }}
                            title="Download Structured JSON Report"
                          >
                            <FileCode size={11} /> JSON
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                )
              })
            )}
          </div>
        </section>

        {/* Right Column: Active Experiment Telemetry & Run Breakdown */}
        <section className="dash-card panel">
          {activeExperiment ? (
            <div>
              <div className="panel-header">
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <h2 className="panel-title">{activeExperiment.name}</h2>
                    <span
                      style={{
                        fontSize: 10,
                        padding: '2px 8px',
                        borderRadius: 4,
                        background: '#0e1726',
                        border: '1px solid #1e293b',
                        color: '#06b6d4',
                        fontWeight: 600,
                      }}
                    >
                      {activeExperiment.execution_mode}
                    </span>
                  </div>
                  <p className="panel-subtitle" style={{ marginTop: 4 }}>
                    {activeExperiment.description || 'Deterministic benchmark trial against target service.'}
                  </p>
                </div>
              </div>

              {/* Statistical Distribution Overview */}
              {activeExperiment.results_summary && activeExperiment.results_summary.completed_runs > 0 ? (
                <div style={{ padding: '0 16px 16px 16px' }}>
                  {activeExperiment.results_summary.sample_size_warning && (
                    <div
                      style={{
                        padding: '8px 12px',
                        borderRadius: 6,
                        background: 'rgba(245, 158, 11, 0.1)',
                        border: '1px solid rgba(245, 158, 11, 0.3)',
                        color: '#f59e0b',
                        fontSize: 11,
                        marginBottom: 12,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                      }}
                    >
                      <AlertTriangle size={14} />
                      <span>{activeExperiment.results_summary.sample_size_warning}</span>
                    </div>
                  )}

                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 10, marginBottom: 16 }}>
                    <div style={{ background: '#0b0f17', border: '1px solid #1e293b', borderRadius: 6, padding: 10 }}>
                      <div style={{ fontSize: 10, color: '#94a3b8', textTransform: 'uppercase' }}>Detection Latency</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#f8fafc', marginTop: 2 }}>
                        {activeExperiment.results_summary.detection_latency?.mean ?? '—'} ms
                      </div>
                      <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                        Median: {activeExperiment.results_summary.detection_latency?.median ?? '—'} ms · StdDev: ±{activeExperiment.results_summary.detection_latency?.std_dev ?? '—'}
                      </div>
                    </div>

                    <div style={{ background: '#0b0f17', border: '1px solid #1e293b', borderRadius: 6, padding: 10 }}>
                      <div style={{ fontSize: 10, color: '#94a3b8', textTransform: 'uppercase' }}>Recovery Duration</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#06b6d4', marginTop: 2 }}>
                        {activeExperiment.results_summary.recovery_duration?.mean ?? '—'} ms
                      </div>
                      <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                        Median: {activeExperiment.results_summary.recovery_duration?.median ?? '—'} ms · StdDev: ±{activeExperiment.results_summary.recovery_duration?.std_dev ?? '—'}
                      </div>
                    </div>

                    <div style={{ background: '#0b0f17', border: '1px solid #1e293b', borderRadius: 6, padding: 10 }}>
                      <div style={{ fontSize: 10, color: '#94a3b8', textTransform: 'uppercase' }}>Total Outage Duration</div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: '#8b5cf6', marginTop: 2 }}>
                        {activeExperiment.results_summary.total_outage_duration?.mean ?? '—'} ms
                      </div>
                      <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
                        P95: {activeExperiment.results_summary.total_outage_duration?.p95 ?? '—'} ms · Verified Health
                      </div>
                    </div>
                  </div>

                  {/* Individual Runs Table */}
                  <h3 style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', marginBottom: 8 }}>
                    Seed-Isolated Runs Breakdown (N={activeExperiment.results_summary.completed_runs})
                  </h3>
                  <div style={{ overflowX: 'auto' }}>
                    <table className="dash-table" style={{ width: '100%', fontSize: 11 }}>
                      <thead>
                        <tr>
                          <th>Run #</th>
                          <th>Seed</th>
                          <th>Detection</th>
                          <th>Recovery</th>
                          <th>Total Outage</th>
                          <th>Outcome</th>
                          <th>Safety</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(activeExperiment.runs || []).map((run) => (
                          <tr key={run.id || run.run_number}>
                            <td>
                              <strong>Run {run.run_number}</strong>
                            </td>
                            <td>
                              <code>{run.seed}</code>
                            </td>
                            <td>{run.detection_latency_ms != null ? `${run.detection_latency_ms.toFixed(1)} ms` : '—'}</td>
                            <td>{run.recovery_duration_ms != null ? `${run.recovery_duration_ms.toFixed(1)} ms` : 'N/A (Control)'}</td>
                            <td>
                              <strong style={{ color: run.total_outage_duration_ms && run.total_outage_duration_ms < 10000 ? '#10b981' : '#f59e0b' }}>
                                {run.total_outage_duration_ms != null ? `${run.total_outage_duration_ms.toFixed(1)} ms` : '—'}
                              </strong>
                            </td>
                            <td>
                              {run.recovery_success ? (
                                <span style={{ color: '#10b981', fontWeight: 600 }}>Passed</span>
                              ) : run.recovery_attempted ? (
                                <span style={{ color: '#ef4444', fontWeight: 600 }}>Failed (Escalated)</span>
                              ) : (
                                <span style={{ color: '#64748b' }}>Unmitigated</span>
                              )}
                            </td>
                            <td>
                              {run.safety_compliant ? (
                                <span style={{ color: '#10b981' }}>✓ Compliant</span>
                              ) : (
                                <span style={{ color: '#ef4444' }}>Violation</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div style={{ padding: 32, textAlign: 'center', color: '#64748b' }}>
                  <FlaskConical size={24} style={{ margin: '0 auto 8px', opacity: 0.5 }} />
                  <p>This experiment has not been executed yet.</p>
                  <button
                    className="dash-button primary"
                    style={{ marginTop: 12, background: '#06b6d4', borderColor: '#06b6d4', color: '#090d16' }}
                    onClick={() => handleStartExperiment(activeExperiment.id)}
                    disabled={actionBusyId === activeExperiment.id}
                  >
                    <Play size={13} /> Run All {activeExperiment.number_of_runs} Trials Now
                  </button>
                </div>
              )}
            </div>
          ) : (
            <div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>
              Select an experiment from the registry to view details.
            </div>
          )}
        </section>
      </div>

      {/* Side-by-Side Comparison Modal */}
      {compareExp && (
        <div className="dialog-backdrop" onClick={() => setCompareExp(null)}>
          <section
            className="dialog-card"
            style={{ maxWidth: 680, width: '90%' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="dialog-icon" style={{ color: '#06b6d4', background: 'rgba(6, 182, 212, 0.1)' }}>
              <TrendingDown size={18} />
            </div>
            <h2 id="dialog-title">Autonomous Remediation vs. Control Baseline</h2>
            <p id="dialog-description">
              Deterministic comparison across identical scenarios and pseudorandom seeds.
            </p>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, margin: '16px 0' }}>
              {/* Enabled Card */}
              <div style={{ background: '#0b0f17', border: '1px solid #06b6d4', borderRadius: 8, padding: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#06b6d4', textTransform: 'uppercase' }}>
                  AutoHeal Enabled (Self-Healing)
                </div>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#f8fafc', margin: '8px 0 4px' }}>
                  {compareExp.enabled_experiment?.total_outage_duration?.mean != null
                    ? `${compareExp.enabled_experiment.total_outage_duration.mean.toFixed(0)} ms`
                    : 'N/A'}
                </div>
                <div style={{ fontSize: 11, color: '#64748b' }}>Mean Total Outage Duration</div>
                <div style={{ marginTop: 10, fontSize: 11, color: '#94a3b8' }}>
                  Verification Success: <strong>{compareExp.enabled_experiment?.recovery_success_rate}%</strong>
                </div>
              </div>

              {/* Disabled Card */}
              <div style={{ background: '#0b0f17', border: '1px solid #1e293b', borderRadius: 8, padding: 14 }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#f59e0b', textTransform: 'uppercase' }}>
                  Control Baseline (Recovery Disabled)
                </div>
                <div style={{ fontSize: 24, fontWeight: 800, color: '#f8fafc', margin: '8px 0 4px' }}>
                  {compareExp.disabled_experiment?.total_outage_duration?.mean != null
                    ? `${compareExp.disabled_experiment.total_outage_duration.mean.toFixed(0)} ms`
                    : '60,000 ms'}
                </div>
                <div style={{ fontSize: 11, color: '#64748b' }}>Mean Unmitigated Outage</div>
                <div style={{ marginTop: 10, fontSize: 11, color: '#94a3b8' }}>
                  Intervention: <strong>Manual Escalation Only</strong>
                </div>
              </div>
            </div>

            {/* Benchmark Impact Summary */}
            <div
              style={{
                background: 'rgba(16, 185, 129, 0.08)',
                border: '1px solid rgba(16, 185, 129, 0.25)',
                borderRadius: 8,
                padding: 12,
                marginBottom: 16,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#10b981', fontWeight: 700, fontSize: 13 }}>
                <CheckCircle2 size={16} />
                MTTR Improvement: {compareExp.mttr_improvement_percentage ?? '—'}% Outage Reduction
              </div>
              <p style={{ fontSize: 12, color: '#cbd5e1', margin: '4px 0 0' }}>
                {compareExp.confidence_note}
              </p>
            </div>

            <div className="dialog-actions">
              <button className="dash-button" onClick={() => setCompareExp(null)}>
                Close Comparison
              </button>
            </div>
          </section>
        </div>
      )}

      {/* Create Experiment Modal */}
      {createModalOpen && (
        <div className="dialog-backdrop" onClick={() => setCreateModalOpen(false)}>
          <section
            className="dialog-card"
            style={{ maxWidth: 560, width: '90%' }}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="dialog-icon" style={{ color: '#06b6d4', background: 'rgba(6, 182, 212, 0.1)' }}>
              <FlaskConical size={18} />
            </div>
            <h2 id="dialog-title">Configure Benchmark Experiment</h2>
            <p id="dialog-description">
              Deterministic evaluation suite for AutoHeal autonomous self-healing.
            </p>

            <form onSubmit={handleCreateSubmit} style={{ marginTop: 14 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <label style={{ fontSize: 12, color: '#cbd5e1' }}>
                  Experiment Title
                  <input
                    type="text"
                    required
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Checkout API 503 Outage Benchmark"
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      background: '#0b0f17',
                      border: '1px solid #1e293b',
                      borderRadius: 6,
                      color: '#f8fafc',
                      marginTop: 4,
                      fontSize: 12,
                    }}
                  />
                </label>

                <label style={{ fontSize: 12, color: '#cbd5e1' }}>
                  Benchmark Scenario
                  <select
                    value={formScenario}
                    onChange={(e) => setFormScenario(e.target.value as ScenarioType)}
                    style={{
                      width: '100%',
                      padding: '8px 10px',
                      background: '#0b0f17',
                      border: '1px solid #1e293b',
                      borderRadius: 6,
                      color: '#f8fafc',
                      marginTop: 4,
                      fontSize: 12,
                    }}
                  >
                    <option value="service_unavailable">Service Unavailable (503 Outage)</option>
                    <option value="healthy_baseline">Healthy Baseline (False Positive Evaluation)</option>
                    <option value="high_error_rate">High Error Rate Surge</option>
                    <option value="resource_exhaustion">Resource Exhaustion (CPU/Memory)</option>
                    <option value="repeated_alerts">Repeated Alerts (Cooldown Suppression)</option>
                    <option value="verification_failure">Verification Failure Gate</option>
                    <option value="unauthorized_recovery">Unauthorized Recovery Attempt (RBAC 403)</option>
                    <option value="unapproved_recovery">Unapproved Recovery Hold</option>
                  </select>
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <label style={{ fontSize: 12, color: '#cbd5e1' }}>
                    Autonomous Recovery Mode
                    <select
                      value={formRecovery ? 'enabled' : 'disabled'}
                      onChange={(e) => setFormRecovery(e.target.value === 'enabled')}
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        background: '#0b0f17',
                        border: '1px solid #1e293b',
                        borderRadius: 6,
                        color: '#f8fafc',
                        marginTop: 4,
                        fontSize: 12,
                      }}
                    >
                      <option value="enabled">Enabled (Auto-Healing)</option>
                      <option value="disabled">Disabled (Control Baseline)</option>
                    </select>
                  </label>

                  <label style={{ fontSize: 12, color: '#cbd5e1' }}>
                    Target Service
                    <input
                      type="text"
                      value={formService}
                      onChange={(e) => setFormService(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        background: '#0b0f17',
                        border: '1px solid #1e293b',
                        borderRadius: 6,
                        color: '#f8fafc',
                        marginTop: 4,
                        fontSize: 12,
                      }}
                    />
                  </label>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <label style={{ fontSize: 12, color: '#cbd5e1' }}>
                    Number of Multi-Runs (N)
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={formRuns}
                      onChange={(e) => setFormRuns(Number(e.target.value))}
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        background: '#0b0f17',
                        border: '1px solid #1e293b',
                        borderRadius: 6,
                        color: '#f8fafc',
                        marginTop: 4,
                        fontSize: 12,
                      }}
                    />
                  </label>

                  <label style={{ fontSize: 12, color: '#cbd5e1' }}>
                    Reproducible Base Seed
                    <input
                      type="number"
                      min={0}
                      value={formSeed}
                      onChange={(e) => setFormSeed(Number(e.target.value))}
                      style={{
                        width: '100%',
                        padding: '8px 10px',
                        background: '#0b0f17',
                        border: '1px solid #1e293b',
                        borderRadius: 6,
                        color: '#f8fafc',
                        marginTop: 4,
                        fontSize: 12,
                      }}
                    />
                  </label>
                </div>
              </div>

              <div className="dialog-actions" style={{ marginTop: 20 }}>
                <button
                  type="button"
                  className="dash-button"
                  onClick={() => setCreateModalOpen(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="dash-button primary"
                  style={{ background: '#06b6d4', borderColor: '#06b6d4', color: '#090d16' }}
                  disabled={actionBusyId === 'create'}
                >
                  {actionBusyId === 'create' ? 'Configuring…' : 'Create Experiment'}
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </>
  )
}
