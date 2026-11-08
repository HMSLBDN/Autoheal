import Link from 'next/link'
import { Activity, AlertTriangle, ArrowDownRight, ArrowRight, ArrowUpRight, Boxes, Check, CheckCircle2, ChevronRight, CircleGauge, Clock3, Database, GitBranch, GitPullRequest, LockKeyhole, Network, RotateCcw, Server, ShieldCheck, Signal, Workflow, Zap } from 'lucide-react'
import { Navbar } from './navbar'
import { Brand } from './brand'
import { Reveal } from './reveal'
import { FeatureCards } from './feature-cards'
import { ShowcaseTabs } from './showcase-tabs'
import { AvailabilityChart, IncidentAreaChart, MiniTrend } from '@/components/dashboard/charts'
import { demoAnalytics } from '@/lib/demo/mock-data'

const activityRows = [
  { title: 'Elevated API error rate', service: 'customer-web', time: '2 min ago', status: 'Investigating' },
  { title: 'Connection pool normalized', service: 'checkout-api', time: '18 min ago', status: 'Verified' },
  { title: 'Worker deployment restarted', service: 'event-worker', time: '1 hr ago', status: 'Resolved' },
]

const integrationList = [
  { name: 'Docker', mark: 'D', detail: 'Container runtime', tone: '#74b9ff' },
  { name: 'Kubernetes', mark: 'K8', detail: 'Orchestration', tone: '#6d9dff' },
  { name: 'Prometheus', mark: 'P', detail: 'Metrics collection', tone: '#ff9f59' },
  { name: 'Grafana', mark: 'G', detail: 'Observability', tone: '#ffbb62' },
  { name: 'GitHub', mark: 'GH', detail: 'Source control', tone: '#e5eaf0' },
  { name: 'Actions', mark: 'CI', detail: 'Delivery pipelines', tone: '#8c82ff' },
  { name: 'PostgreSQL', mark: 'Pg', detail: 'Relational database', tone: '#91b5ff' },
  { name: 'FastAPI', mark: 'API', detail: 'Application services', tone: '#35d6c5' },
]

export function MarketingPage() {
  return <div className="site-shell">
    <Navbar />
    <main>
      <section className="hero" id="top">
        <div className="site-container hero-grid">
          <div>
            <div className="status-pill"><span className="pulse" /> AI-ASSISTED DEVOPS AUTOMATION</div>
            <h1 className="hero-title">Your infrastructure.<br /><span className="accent-word">Always one step ahead.</span></h1>
            <p className="hero-copy">Detect failures before they become downtime. Diagnose with evidence. Recover through controlled policies. Verify every outcome.</p>
            <div className="hero-ctas"><a className="btn btn-primary" href="#platform">Explore platform <ArrowRight size={14} /></a><a className="btn btn-secondary" href="#platform"><Activity size={14} /> View live demo</a></div>
            <div className="hero-proof"><span><Check size={13} /> Intelligent monitoring</span><span><Check size={13} /> Controlled recovery</span><span><Check size={13} /> Verified outcomes</span></div>
          </div>
          <Reveal>
            <div className="network-card surface" aria-label="Illustration of connected application, service, database, and monitoring nodes">
              <div className="network-glow" /><div className="network-orbit" /><div className="network-orbit orbit-two" /><div className="network-orbit orbit-three" />
              <svg className="network-lines" viewBox="0 0 600 430" preserveAspectRatio="none" aria-hidden="true">
                <path d="M300 215 L300 72 M300 215 L111 155 M300 215 L486 155 M300 215 L165 348 M300 215 L455 346" />
              </svg>
              <div className="network-node node-app"><span className="node-icon"><Activity size={17} /></span><strong>Application</strong><small><span className="status-dot" style={{ display: 'inline-block', marginRight: 5 }} /> Healthy · 99.98%</small></div>
              <div className="network-node node-top"><span className="node-icon"><Signal size={13} /></span><strong>Telemetry</strong><small>Metrics · traces</small></div>
              <div className="network-node node-left"><span className="node-icon"><Server size={13} /></span><strong>API service</strong><small>Latency stable</small></div>
              <div className="network-node node-right"><span className="node-icon"><Database size={13} /></span><strong>PostgreSQL</strong><small>Pool healthy</small></div>
              <div className="network-node node-bottom-left"><span className="node-icon"><Boxes size={13} /></span><strong>Containers</strong><small>3 workloads</small></div>
              <div className="network-node node-bottom-right"><span className="node-icon"><GitBranch size={13} /></span><strong>Deployments</strong><small>Release tracked</small></div>
              <div className="network-caption"><i /> DEMONSTRATION ENVIRONMENT · NOT CONNECTED TO LIVE INFRASTRUCTURE</div>
            </div>
          </Reveal>
        </div>
      </section>

      <div className="stat-strip"><div className="site-container stat-strip-inner"><span><b>01</b> Monitor service health</span><span><ArrowRight size={13} /></span><span><b>02</b> Correlate evidence</span><span><ArrowRight size={13} /></span><span><b>03</b> Gate recovery actions</span><span><ArrowRight size={13} /></span><span><b>04</b> Verify outcomes</span></div></div>

      <section className="section" id="platform">
        <div className="site-container">
          <Reveal><div className="section-kicker">Live system status · demo data</div><h2 className="section-title">One clear view of what is happening.</h2><p className="section-copy">A product preview built around the signals your team needs to make the next decision. These illustrative values are not connected to customer infrastructure.</p></Reveal>
          <Reveal delay={.08}>
            <div className="preview-window">
              <div className="window-bar"><span className="window-dot" /><span className="window-dot" /><span className="window-dot" /><span style={{ marginLeft: 8 }}>workspace / overview</span><span style={{ marginLeft: 'auto' }} className="status-chip">DEMO ENVIRONMENT</span></div>
              <div className="preview-grid">
                <div className="preview-metric"><small>Service availability</small><strong>99.94%</strong><em>+0.08% this week</em><div className="preview-chart"><AvailabilityChart data={demoAnalytics.history} compact /></div></div>
                <div className="preview-metric"><small>Active incidents</small><strong>02</strong><em style={{ color: '#f5b34b' }}>1 needs approval</em></div>
                <div className="preview-metric"><small>Detection latency</small><strong>42s</strong><em>Median · 7 days</em></div>
                <div className="preview-metric"><small>Verified recoveries</small><strong>94.2%</strong><em>Demo window · 7 days</em></div>
              </div>
              <div className="preview-lower">
                <div className="preview-panel"><div className="preview-panel-title">Incident activity <span style={{ color: '#7b899d', fontWeight: 400 }}>Last 7 days</span></div><div style={{ height: 130, marginTop: 12 }}><IncidentAreaChart data={demoAnalytics.history} compact /></div></div>
                <div className="preview-panel"><div className="preview-panel-title">Recent activity <span style={{ color: '#35d6c5', fontWeight: 500 }}>View incidents <ArrowUpRight size={11} style={{ verticalAlign: 'middle' }} /></span></div>{activityRows.map((row) => <div className="activity-row" key={row.title}><span className={`status-dot${row.status === 'Investigating' ? ' degraded' : ''}`} /><span>{row.title}<small style={{ display: 'block', color: '#75849a', marginTop: 3 }}>{row.service}</small></span><span className="activity-time">{row.time}</span></div>)}</div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      <section className="section" id="why" style={{ background: 'linear-gradient(180deg, transparent, rgba(13,18,32,.5), transparent)' }}>
        <div className="site-container">
          <Reveal><div className="section-kicker">A better incident loop</div><h2 className="section-title">Stop fighting fires.<br />Start preventing downtime.</h2><p className="section-copy">Keep your team in control while removing the repetitive work between alert and verified resolution.</p></Reveal>
          <div className="comparison-grid">
            <Reveal className="surface comparison-card"><div className="comparison-heading"><span>Traditional response</span><span className="status-chip degraded">Reactive</span></div><div className="comparison-list">{['Manual incident investigation', 'Signals scattered across tools', 'Repetitive troubleshooting', 'Recovery without clear verification', 'Slow handoffs between teams'].map((text) => <div className="comparison-item" key={text}><span className="comparison-icon"><ArrowDownRight size={12} /></span>{text}</div>)}</div></Reveal>
            <Reveal className="surface comparison-card auto" delay={.1}><div className="comparison-heading"><span>AutoHeal workflow</span><span className="status-chip">Evidence-led</span></div><div className="comparison-list">{['Automated failure detection', 'Evidence-based diagnosis', 'Policy-checked recovery', 'Post-action health verification', 'Centralized incident history'].map((text) => <div className="comparison-item" key={text}><span className="comparison-icon"><Check size={12} /></span>{text}</div>)}</div></Reveal>
          </div>
        </div>
      </section>

      <section className="section" id="features">
        <div className="site-container">
          <Reveal><div className="section-kicker">Core capabilities</div><h2 className="section-title">Everything your infrastructure needs to heal.</h2><p className="section-copy">A connected workflow from first signal to verified service health. Select a capability to see how its guardrails work.</p></Reveal>
          <Reveal delay={.08}><FeatureCards /></Reveal>
        </div>
      </section>

      <section className="section" id="workflow" style={{ background: 'rgba(13,18,32,.46)' }}>
        <div className="site-container">
          <Reveal><div className="section-kicker">How it works</div><h2 className="section-title">From incident to recovery.<br />Automatically, with control.</h2><p className="section-copy">Every step is observable. Recovery policies define what can run, who approves it, and when an incident can be resolved.</p></Reveal>
          <Reveal delay={.06}><div className="workflow">{[
            { icon: Signal, title: 'Monitor', text: 'Collect service and infrastructure signals.' },
            { icon: AlertTriangle, title: 'Detect', text: 'Identify configured unhealthy conditions.' },
            { icon: GitPullRequest, title: 'Diagnose', text: 'Correlate metrics, logs, and releases.' },
            { icon: Workflow, title: 'Recover', text: 'Run an approved recovery policy.' },
            { icon: CircleGauge, title: 'Verify', text: 'Evaluate health checks after action.' },
            { icon: CheckCircle2, title: 'Resolve', text: 'Close or escalate based on evidence.' },
          ].map((step, index) => { const Icon = step.icon; return <div className="workflow-step" key={step.title}><div className="workflow-dot"><Icon size={17} /></div><h3>0{index + 1} · {step.title}</h3><p>{step.text}</p></div> })}</div></Reveal>
        </div>
      </section>

      <section className="section">
        <div className="site-container">
          <Reveal><div className="section-kicker">Product preview</div><h2 className="section-title">Designed for the work after the alert.</h2><p className="section-copy">Switch between monitoring, investigation, recovery, and analytics. Each preview uses illustrative sample data.</p></Reveal>
          <Reveal delay={.07}><ShowcaseTabs /></Reveal>
        </div>
      </section>

      <section className="section" style={{ background: 'rgba(13,18,32,.45)' }}>
        <div className="site-container policy-layout">
          <Reveal><div className="section-kicker">Smart recovery engine</div><h2 className="section-title">Recovery that follows rules. Not guesswork.</h2><p className="section-copy">AI can help interpret evidence and suggest a next step. The recovery engine only executes actions that your team has explicitly allowed.</p>
            <div className="policy-points">{[
              'Allowlisted recovery operations and restricted permissions',
              'Human approval gates for sensitive changes',
              'Retry limits, cooldowns, and policy preconditions',
              'Verification before resolution; escalation when checks fail',
            ].map((text) => <div className="policy-point" key={text}><ShieldCheck size={14} />{text}</div>)}</div>
          </Reveal>
          <Reveal delay={.1}><div className="policy-console surface"><div className="console-title"><span>Recovery policy · checkout-api</span><span className="console-status">● Approval required</span></div>
            <div className="console-step"><span className="console-step-icon"><AlertTriangle size={13} /></span><div><strong>Incident · High error rate</strong><span>1.84% error rate crossed configured 1.0% threshold</span></div></div>
            <div className="console-step"><span className="console-step-icon"><ScanSearchIcon /></span><div><strong>Diagnosis · Correlated evidence</strong><span>Release change and upstream timeouts identified</span></div></div>
            <div className="console-step"><span className="console-step-icon"><LockKeyhole size={13} /></span><div><strong>Suggested action · Roll back release</strong><span>Allowlisted · maximum 1 attempt · cooldown 15 minutes</span></div></div>
            <div className="console-step"><span className="console-step-icon" style={{ color: '#f5b34b', background: 'rgba(245,158,11,.1)' }}><Clock3 size={13} /></span><div><strong>Approval · Pending an operator</strong><span>No infrastructure command runs until authorized</span></div></div>
            <div className="console-step"><span className="console-step-icon"><CircleGauge size={13} /></span><div><strong>Verification · Pending</strong><span>Incident resolves only after configured health checks pass</span></div></div>
          </div></Reveal>
        </div>
      </section>

      <section className="section">
        <div className="site-container">
          <Reveal><div className="section-kicker">Performance analytics · demo data</div><h2 className="section-title">Every incident becomes an opportunity to improve.</h2><p className="section-copy">Make response patterns visible with transparent, clearly labeled sample analytics. Connect a backend to replace this demonstration data.</p></Reveal>
          <div className="analytics-grid">
            {[['Detection latency', '42 sec', 'Median · illustrative'], ['Recovery duration', '6.4 min', 'Mean · illustrative'], ['Verified recovery', '94.2%', '7-day sample window'], ['False-positive rate', '2.1%', '7-day sample window'], ['Service availability', '99.94%', '7-day sample window'], ['Incidents reviewed', '18', 'Sample data only']].map(([label, value, foot], index) => <Reveal key={label} delay={index * .035}><div className="analytics-card surface"><small>{label}</small><strong>{value}</strong><span>{foot}</span></div></Reveal>)}
          </div>
          <Reveal><div className="analytics-chart surface" style={{ padding: 17 }}><div className="panel-header"><div><div className="panel-title">Incident and recovery trend</div><div className="panel-subtitle">Illustrative, last 7 days</div></div><div className="status-chip">DEMO DATA</div></div><div style={{ height: 175, marginTop: 12 }}><IncidentAreaChart data={demoAnalytics.history} /></div><div className="analytics-note">For product demonstration only. Values are not customer or production results.</div></div></Reveal>
        </div>
      </section>

      <section className="section" id="integrations" style={{ background: 'rgba(13,18,32,.45)' }}>
        <div className="site-container">
          <Reveal><div className="section-kicker">Integrations</div><h2 className="section-title">Connect your existing DevOps ecosystem.</h2><p className="section-copy">Bring the tools your team already uses into a single incident workflow. No service is shown as connected until the backend confirms it.</p></Reveal>
          <Reveal delay={.07}><div className="integration-grid">{integrationList.map((item) => <div className="integration-card" key={item.name}><span className="integration-icon" style={{ color: item.tone, fontWeight: 700, fontSize: 10 }}>{item.mark}</span><span><strong>{item.name}</strong><small>{item.detail} · Available</small></span><span style={{ marginLeft: 'auto', color: '#6e7c90', fontSize: 8 }}>Not connected</span></div>)}</div></Reveal>
        </div>
      </section>

      <section className="section" id="security">
        <div className="site-container">
          <Reveal><div className="section-kicker">Security and governance</div><h2 className="section-title">Automation with control built in.</h2><p className="section-copy">Keep infrastructure changes within explicit permission boundaries. This product preview makes no certification or compliance claims.</p></Reveal>
          <div className="security-grid">{[
            { icon: LockKeyhole, title: 'Restricted permissions', copy: 'Recovery operations are allowlisted and constrained to scoped backend permissions.' },
            { icon: CheckCircle2, title: 'Approval-based actions', copy: 'Require a human review when a recovery policy marks an operation as sensitive.' },
            { icon: GitBranch, title: 'Complete audit history', copy: 'Keep incident evidence, policy decisions, approvals, and execution outcomes together.' },
            { icon: Network, title: 'Secure integrations', copy: 'Connect services through the backend with least-privilege credentials.' },
          ].map((item, index) => { const Icon = item.icon; return <Reveal key={item.title} delay={index * .04}><div className="security-card surface"><Icon size={18} /><h3>{item.title}</h3><p>{item.copy}</p></div></Reveal> })}</div>
        </div>
      </section>

      <section className="section" style={{ paddingTop: 25 }}>
        <div className="site-container"><Reveal><div className="cta-panel surface"><div className="section-kicker">Ready when you are</div><h2>Your infrastructure deserves more than monitoring.</h2><p>Move beyond alerts. Build a workflow that detects, diagnoses, recovers, and verifies—with your policies in control.</p><div className="hero-ctas"><Link className="btn btn-primary" href="/dashboard">Explore dashboard <ArrowRight size={14} /></Link><Link className="btn btn-secondary" href="/register">Get started <ArrowUpRight size={14} /></Link></div></div></Reveal></div>
      </section>
    </main>
    <footer className="site-footer"><div className="site-container"><div className="footer-grid"><div className="footer-brand"><Brand /><p>Detect. Diagnose. Recover. Verify.<br />Controlled incident response for modern infrastructure.</p></div>
      <div className="footer-col"><strong>Platform</strong><a href="#platform">Overview</a><a href="#features">Capabilities</a><a href="#workflow">How it works</a><a href="#integrations">Integrations</a></div>
      <div className="footer-col"><strong>Governance</strong><a href="#security">Security model</a><a href="#features">Monitoring</a><a href="#features">Recovery engine</a><a href="#platform">Analytics preview</a></div>
      <div className="footer-col"><strong>Workspace</strong><Link href="/dashboard">Dashboard demo</Link><Link href="/login">Sign in</Link><Link href="/register">Get started</Link><a href="#top">Back to top ↑</a></div>
    </div><div className="footer-bottom"><span>© 2026 AutoHeal DevOps. Product demonstration.</span><span>Demo metrics are illustrative and are not connected to live infrastructure.</span></div></div></footer>
  </div>
}

function ScanSearchIcon() {
  return <Activity size={13} />
}
