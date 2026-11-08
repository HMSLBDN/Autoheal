'use client'

import { useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { Activity, AlertTriangle, BarChart3, CheckCircle2, CircleDot, Clock3, Server, ShieldCheck } from 'lucide-react'
import { MiniTrend } from '@/components/dashboard/charts'

const tabs = [
  { label: 'Infrastructure monitoring', title: 'See health across every service.', copy: 'Availability, latency, and error signals stay close to the services they describe. Use this view to spot drift before it becomes an incident.', metric: '99.94%', metricLabel: 'Demo availability', icon: Server, value: '42 ms', valueLabel: 'Detection latency' },
  { label: 'Incident investigation', title: 'Move from alert to evidence.', copy: 'Inspect the alert, release timeline, and correlated signals without switching between fragmented tools.', metric: 'INC-2841', metricLabel: 'Elevated API error rate', icon: AlertTriangle, value: '3 signals', valueLabel: 'Correlated evidence' },
  { label: 'Recovery engine', title: 'Make every action accountable.', copy: 'Review policy checks, required approvals, execution state, and health verification in a single recovery timeline.', metric: 'Approval', metricLabel: 'Gate required', icon: ShieldCheck, value: 'Pending', valueLabel: 'Verification state' },
  { label: 'Analytics', title: 'Learn from the incident history.', copy: 'Understand detection time, recovery duration, and availability trends using clearly identified sample data.', metric: '94.2%', metricLabel: 'Demo recovery success', icon: BarChart3, value: '6.4 min', valueLabel: 'Mean recovery time' },
]

export function ShowcaseTabs() {
  const [selected, setSelected] = useState(0)
  const reduceMotion = useReducedMotion()
  const tab = tabs[selected]
  const Icon = tab.icon
  return <>
    <div className="showcase-tabs" role="tablist" aria-label="Product preview">
      {tabs.map((item, index) => <button key={item.label} id={`showcase-tab-${index}`} role="tab" aria-selected={selected === index} aria-controls="showcase-panel" className={`showcase-tab${selected === index ? ' active' : ''}`} onClick={() => setSelected(index)}>{item.label}</button>)}
    </div>
    <div className="showcase-panel" id="showcase-panel" role="tabpanel" aria-labelledby={`showcase-tab-${selected}`}>
      <div className="showcase-copy surface">
        <span className="section-kicker">Product preview / 0{selected + 1}</span>
        <h3 style={{ marginTop: 15 }}>{tab.title}</h3>
        <p>{tab.copy}</p>
        <div className="feature-more"><CheckCircle2 size={13} /> Demo data — no infrastructure connected</div>
      </div>
      <div className="showcase-preview surface">
        <AnimatePresence mode="wait">
          <motion.div key={selected} initial={reduceMotion ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={reduceMotion ? undefined : { opacity: 0, y: -5 }} transition={{ duration: .22 }}>
            <div className="showcase-preview-top"><span><Icon size={13} style={{ verticalAlign: 'middle', marginRight: 8, color: '#35d6c5' }} />{tab.label}</span><span className="status-chip">Demo environment</span></div>
            <div className="showcase-preview-grid">
              <div className="showcase-tile"><small>{tab.metricLabel}</small><strong style={{ fontSize: selected === 1 ? 17 : 21 }}>{tab.metric}</strong><div style={{ height: 44, marginTop: 7 }}><MiniTrend /></div></div>
              <div className="showcase-tile"><small>{tab.valueLabel}</small><strong>{tab.value}</strong><div className="activity-row"><span className="status-dot" /><span>Policy checks enabled</span><span className="activity-time">now</span></div></div>
              <div className="showcase-tile"><small>Service activity</small><div style={{ marginTop: 12 }} className="activity-row"><span className="status-dot" /><span>checkout-api</span><span className="status-chip">Healthy</span></div><div className="activity-row"><span className="status-dot degraded" /><span>customer-web</span><span className="status-chip degraded">Degraded</span></div></div>
              <div className="showcase-tile"><small>Latest event</small><div style={{ marginTop: 11 }} className="activity-row"><Clock3 size={12} /><span>Health check completed</span></div><div className="activity-row"><CircleDot size={12} /><span>Approval gate unchanged</span></div></div>
            </div>
          </motion.div>
        </AnimatePresence>
      </div>
    </div>
  </>
}
