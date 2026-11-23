import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('AutoHeal DevOps — UI Skeletons, Empty States & Error Resilience', () => {
  const rootDir = process.cwd()

  it('components/ui/skeleton.tsx exports accessible skeleton components', () => {
    const skeletonCode = fs.readFileSync(path.join(rootDir, 'components/ui/skeleton.tsx'), 'utf8')
    assert(skeletonCode.includes('export function Skeleton('), 'Skeleton must be exported')
    assert(skeletonCode.includes('export function MetricCardSkeleton('), 'MetricCardSkeleton must be exported')
    assert(skeletonCode.includes('export function TableSkeleton('), 'TableSkeleton must be exported')
    assert(skeletonCode.includes('export function ChartSkeleton('), 'ChartSkeleton must be exported')
    assert(skeletonCode.includes('export function ListSkeleton('), 'ListSkeleton must be exported')
    assert(skeletonCode.includes('role="status"'), 'Skeletons must include role="status"')
  })

  it('app/globals.css defines skeleton-shimmer animation for dark cybernetic aesthetic', () => {
    const globalsCss = fs.readFileSync(path.join(rootDir, 'app/globals.css'), 'utf8')
    assert(globalsCss.includes('skeleton-shimmer'), 'globals.css must define skeleton-shimmer keyframes')
    assert(globalsCss.includes('.skeleton-shimmer'), 'globals.css must define skeleton-shimmer utility class')
  })

  it('components/dashboard/data-views.tsx implements EmptyState for all dashboard sections', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(dataViewsCode.includes('export function EmptyState('), 'EmptyState must be exported')
    assert(dataViewsCode.includes('No monitored services'), 'Empty state for no monitored services')
    assert(dataViewsCode.includes('No active incidents'), 'Empty state for no active incidents')
    assert(dataViewsCode.includes('No recovery history'), 'Empty state for no recovery history')
    assert(dataViewsCode.includes('No pending approvals'), 'Empty state for no pending approvals')
    assert(dataViewsCode.includes('No matching'), 'Empty state for search filter mismatch')
  })

  it('components/dashboard/data-views.tsx implements localized SectionErrorState with Retry', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(dataViewsCode.includes('export function SectionErrorState('), 'SectionErrorState must be exported')
    assert(dataViewsCode.includes('Retry'), 'SectionErrorState must include Retry button')
    assert(dataViewsCode.includes('role="alert"'), 'SectionErrorState must be accessible with role="alert"')
    assert(dataViewsCode.includes('isAuthExpired'), 'SectionErrorState must detect expired authentication sessions')
  })

  it('dashboard-view.tsx wires section retries directly to SWR resource mutate', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('onRetryServices={() => servicesResource.mutate()}'), 'Services section retry must call mutate')
    assert(dashboardViewCode.includes('onRetryIncidents={() => incidentsResource.mutate()}'), 'Incidents section retry must call mutate')
    assert(dashboardViewCode.includes('onRetryRecoveries={() => recoveriesResource.mutate()}'), 'Recoveries section retry must call mutate')
    assert(dashboardViewCode.includes('onRetryAnalytics={() => analyticsResource.mutate()}'), 'Analytics section retry must call mutate')
  })

  it('demoMode and live backend mode remain strictly segregated in dashboard-view.tsx', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('const demoMode = isDemoMode'), 'Must evaluate demoMode status')
    assert(dashboardViewCode.includes('Demo actions are read-only'), 'Demo actions must be prevented from executing real mutations')
    assert(dashboardViewCode.includes('fallbackData: demoMode ? demoServices : undefined'), 'Demo fallback must only apply in demo mode')
  })
})
