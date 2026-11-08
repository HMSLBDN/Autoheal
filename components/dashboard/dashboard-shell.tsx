'use client'

import { createContext, useContext, useEffect, useState } from 'react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Activity, AlertTriangle, BarChart3, Bell, ChevronDown, Clock3, Command, FileText, Gauge, LayoutDashboard, Menu, Search, Settings2, Workflow, X } from 'lucide-react'
import { Brand } from '@/components/marketing/brand'

type DashboardControls = { query: string; setQuery: (value: string) => void; environment: string; setEnvironment: (value: string) => void }
const DashboardContext = createContext<DashboardControls | null>(null)
export function useDashboardControls() {
  const context = useContext(DashboardContext)
  if (!context) throw new Error('useDashboardControls must be used inside DashboardShell')
  return context
}

const navigation = [
  { label: 'Overview', href: '/dashboard', icon: LayoutDashboard },
  { label: 'Services', href: '/dashboard/services', icon: Activity },
  { label: 'Incidents', href: '/dashboard/incidents', icon: AlertTriangle },
  { label: 'Recovery Center', href: '/dashboard/recovery', icon: Workflow },
  { label: 'Recovery History', href: '/dashboard/history', icon: Clock3 },
  { label: 'Monitoring', href: '/dashboard/monitoring', icon: Gauge },
  { label: 'Analytics', href: '/dashboard/analytics', icon: BarChart3 },
  { label: 'Reports', href: '/dashboard/reports', icon: FileText },
]

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const [query, setQuery] = useState('')
  const [environment, setEnvironment] = useState('all')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [noticeOpen, setNoticeOpen] = useState(false)
  const [profileOpen, setProfileOpen] = useState(false)
  const leaf = pathname === '/dashboard' ? 'Overview' : pathname.split('/')[2]?.replace(/-/g, ' ') ?? 'Overview'

  useEffect(() => {
    const query = window.matchMedia('(max-width: 760px)')
    const syncViewport = () => {
      setIsMobile(query.matches)
      if (!query.matches) setSidebarOpen(false)
    }
    syncViewport()
    query.addEventListener('change', syncViewport)
    return () => query.removeEventListener('change', syncViewport)
  }, [])

  useEffect(() => {
    if (!isMobile || !sidebarOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setSidebarOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [isMobile, sidebarOpen])

  return <DashboardContext.Provider value={{ query, setQuery, environment, setEnvironment }}>
    <div className="dashboard-root">
      {isMobile && sidebarOpen && <button className="sidebar-scrim" type="button" aria-label="Close workspace navigation" onClick={() => setSidebarOpen(false)} />}
      <aside id="workspace-sidebar" className={`dashboard-sidebar${sidebarOpen ? ' open' : ''}`} aria-label="Workspace navigation" aria-hidden={isMobile && !sidebarOpen} inert={isMobile && !sidebarOpen}>
        <div className="sidebar-brand"><Brand /></div>
        <div className="workspace-label">Workspace</div>
        <nav className="sidebar-nav">
          {navigation.map((item) => {
            const Icon = item.icon
            const active = item.href === '/dashboard' ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`)
            return <Link key={item.href} href={item.href} onClick={() => setSidebarOpen(false)} className={`sidebar-link${active ? ' active' : ''}`} aria-current={active ? 'page' : undefined}><Icon aria-hidden="true" />{item.label}</Link>
          })}
        </nav>
        <div className="workspace-label" style={{ marginTop: 16 }}>Manage</div>
        <nav className="sidebar-nav"><Link className={`sidebar-link${pathname === '/dashboard/settings' ? ' active' : ''}`} href="/dashboard/settings" onClick={() => setSidebarOpen(false)}><Settings2 aria-hidden="true" />Settings</Link></nav>
        <div className="sidebar-bottom">
          <div className="sidebar-help"><strong>Need a hand?</strong><p>Explore the demo or connect your API to see live service data.</p><Link className="feature-more" href="/">Explore platform <ChevronDown size={11} style={{ transform: 'rotate(-90deg)' }} /></Link></div>
          <div className="profile-row"><div className="avatar" aria-hidden="true">AH</div><div><div className="profile-name">Demo workspace</div><div className="profile-role">Read-only preview</div></div><ChevronDown size={13} style={{ marginLeft: 'auto', color: '#78869a' }} /></div>
        </div>
      </aside>
      <div className="dashboard-main">
        <header className="dashboard-topbar">
          <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
            <button className="icon-button sidebar-mobile-toggle" aria-controls="workspace-sidebar" onClick={() => setSidebarOpen(!sidebarOpen)} aria-label={sidebarOpen ? 'Close sidebar' : 'Open sidebar'} aria-expanded={sidebarOpen}>{sidebarOpen ? <X size={14} /> : <Menu size={14} />}</button>
            <div className="breadcrumb">Workspace <span style={{ color: '#526176', margin: '0 7px' }}>/</span><strong style={{ textTransform: 'capitalize' }}>{leaf}</strong></div>
          </div>
          <div className="topbar-tools">
            <label className="topbar-search"><Search size={13} aria-hidden="true" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search workspace" aria-label="Search workspace" /><Command size={12} aria-hidden="true" /></label>
            <label className="sr-only" htmlFor="environment-select">Environment</label><select className="topbar-select" id="environment-select" value={environment} onChange={(event) => setEnvironment(event.target.value)}><option value="all">All environments</option><option value="production">Production</option><option value="staging">Staging</option></select>
            <button className="icon-button" aria-label="Demo notifications" onClick={() => setNoticeOpen(!noticeOpen)} aria-expanded={noticeOpen}><Bell size={14} /></button>
            <div style={{ position: 'relative' }}><button className="icon-button" aria-label="Open demo profile menu" onClick={() => setProfileOpen(!profileOpen)} aria-expanded={profileOpen}><span className="avatar" style={{ width: 21, height: 21 }}>AH</span></button>{profileOpen && <div className="profile-popover"><strong>Demo workspace</strong><span>Read-only preview</span><Link href="/dashboard/settings" onClick={() => setProfileOpen(false)}>Workspace settings</Link></div>}</div>
          </div>
        </header>
        {noticeOpen && <div className="notice-strip" style={{ position: 'fixed', top: 70, right: 22, zIndex: 50, width: 290, boxShadow: '0 18px 50px rgba(0,0,0,.4)' }}><strong style={{ color: '#e6edf5' }}>Demo notifications</strong><p style={{ margin: '6px 0 0' }}>Connect a backend to receive real incident alerts and recovery updates.</p></div>}
        <main className="dashboard-content">{children}</main>
      </div>
    </div>
  </DashboardContext.Provider>
}
