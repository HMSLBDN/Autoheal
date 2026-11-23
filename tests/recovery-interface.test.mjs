import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('AutoHeal DevOps — Recovery Approval, Rejection & Diagnostics Interface', () => {
  const rootDir = process.cwd()

  it('ConfirmDialog supports inputPrompt with live character counter and error handling', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('dialog.inputPrompt'), 'ConfirmDialog must check dialog.inputPrompt')
    assert(dashboardViewCode.includes('dialog-char-counter'), 'ConfirmDialog must render character counter')
    assert(dashboardViewCode.includes('maxLength = dialog.inputPrompt?.maxLength ?? 500'), 'ConfirmDialog must use 500 characters max limit')
    assert(dashboardViewCode.includes('Rejection reason cannot exceed'), 'ConfirmDialog must have max length error message')
  })

  it('beginRejection configures danger tone and prompts for optional rejection reason', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('confirmTone: \'danger\''), 'beginRejection must use danger tone')
    assert(dashboardViewCode.includes('Rejection reason (optional)'), 'beginRejection must label reason as optional')
    assert(dashboardViewCode.includes('performRejection(id, inputValue)'), 'beginRejection must forward input value to performRejection')
  })

  it('performRejection trims reason and revalidates SWR resources', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('recoveriesApi.reject(id, trimmedReason)'), 'performRejection must pass trimmedReason')
    assert(dashboardViewCode.includes('recoveriesResource.mutate()'), 'performRejection must revalidate recoveriesResource')
    assert(dashboardViewCode.includes('incidentsResource.mutate()'), 'performRejection must revalidate incidentsResource')
  })

  it('RecoveryTable implements expandable rows with accessible chevron toggles', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(dataViewsCode.includes('const [expandedIds, setExpandedIds] = useState'), 'RecoveryTable must track expanded IDs')
    assert(dataViewsCode.includes('table-expand-btn'), 'RecoveryTable must render expand buttons')
    assert(dataViewsCode.includes('aria-expanded={isExpanded}'), 'Expand button must set aria-expanded')
    assert(dataViewsCode.includes('table-expand-icon'), 'Expand button must render rotating icon')
  })

  it('RecoveryTable clearly distinguishes HEALTH_VERIFIED from VERIFICATION_FAILED', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(dataViewsCode.includes('HEALTH VERIFIED'), 'RecoveryTable must render HEALTH VERIFIED badge')
    assert(dataViewsCode.includes('VERIFICATION FAILED'), 'RecoveryTable must render VERIFICATION FAILED badge')
    assert(dataViewsCode.includes('status-chip completed'), 'HEALTH VERIFIED must use completed status chip')
    assert(dataViewsCode.includes('status-chip failed'), 'VERIFICATION FAILED must use failed status chip')
  })

  it('RecoveryTable handles missing diagnostic output and missing summaries truthfully', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(
      dataViewsCode.includes('Diagnostic telemetry output was not supplied by the backend for this action.'),
      'Must state when diagnostic output was not supplied without inventing data'
    )
    assert(
      dataViewsCode.includes('No execution summary was provided by the backend for this action.'),
      'Must state when execution summary was not provided without inventing data'
    )
  })

  it('RecoveryTable drawer includes complete 8-item audit and execution metadata grid', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(dataViewsCode.includes('Remediation Action'), 'Audit grid must include Remediation Action')
    assert(dataViewsCode.includes('Target Service'), 'Audit grid must include Target Service')
    assert(dataViewsCode.includes('Correlated Incident'), 'Audit grid must include Correlated Incident')
    assert(dataViewsCode.includes('Requested By'), 'Audit grid must include Requested By')
    assert(dataViewsCode.includes('Requested At'), 'Audit grid must include Requested At')
    assert(dataViewsCode.includes('Completed At'), 'Audit grid must include Completed At')
    assert(dataViewsCode.includes('Execution Duration'), 'Audit grid must include Execution Duration')
    assert(dataViewsCode.includes('Governance Mode'), 'Audit grid must include Governance Mode')
  })
})
