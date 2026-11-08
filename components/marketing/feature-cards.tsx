'use client'

import { useState } from 'react'
import { Activity, ArrowUpRight, Check, CircleDot, RotateCcw, ScanSearch, ShieldCheck } from 'lucide-react'

const features = [
  { title: 'Detect', icon: Activity, description: 'Continuously observe availability, latency, error rates, and infrastructure signals.', detail: 'Bring metrics and health checks into one signal stream. Thresholds stay explicit, and every alert links back to the evidence that triggered it.' },
  { title: 'Diagnose', icon: ScanSearch, description: 'Correlate incident evidence to surface probable causes your team can inspect.', detail: 'Review the metric change, release history, and log patterns together. Diagnosis is evidence-led, not an unverified model guess.' },
  { title: 'Recover', icon: RotateCcw, description: 'Run allowlisted recovery actions through policy checks and approval gates.', detail: 'Actions are scoped to approved operations, guarded by cooldowns and retry limits, and held for human review when policy requires it.' },
  { title: 'Verify', icon: ShieldCheck, description: 'Close the loop only after post-recovery health checks pass.', detail: 'Recovery results remain pending until the configured checks confirm service health. Failed verification escalates instead of claiming success.' },
]

export function FeatureCards() {
  const [active, setActive] = useState<number | null>(0)
  return (
    <div className="feature-grid">
      {features.map((feature, index) => {
        const Icon = feature.icon
        const expanded = active === index
        return <button key={feature.title} className={`feature-card surface${expanded ? ' expanded' : ''}`} aria-expanded={expanded} onClick={() => setActive(expanded ? null : index)}>
          <span className="feature-icon"><Icon size={18} /></span>
          <h3>{feature.title}</h3>
          <p>{expanded ? feature.detail : feature.description}</p>
          <span className="feature-more">{expanded ? <><Check size={12} /> Guardrails included</> : <>Explore capability <ArrowUpRight size={12} /></>}</span>
        </button>
      })}
    </div>
  )
}
