import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('AutoHeal DevOps — Downloadable Incident Reports Integration', () => {
  const rootDir = process.cwd()

  it('IncidentDetailView renders both PDF and JSON download buttons', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(dataViewsCode.includes('onDownloadReport(incident.id, \'pdf\')'), 'Must wire PDF download button')
    assert(dataViewsCode.includes('onDownloadReport(incident.id, \'json\')'), 'Must wire JSON download button')
    assert(dataViewsCode.includes('Download PDF Report'), 'Must display Download PDF Report label')
    assert(dataViewsCode.includes('Download JSON Report'), 'Must display Download JSON Report label')
  })

  it('IncidentDetailView prevents duplicate clicks while download is in-flight', () => {
    const dataViewsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/data-views.tsx'), 'utf8')
    assert(dataViewsCode.includes('const isBusy = Boolean(busyId)'), 'Must evaluate isBusy state')
    assert(dataViewsCode.includes('disabled={isBusy}'), 'Download buttons must be disabled when isBusy')
    assert(dataViewsCode.includes('isPdfBusy ? \'Preparing PDF…\' : \'Download PDF Report\''), 'Must indicate PDF loading progress')
    assert(dataViewsCode.includes('isJsonBusy ? \'Preparing JSON…\' : \'Download JSON Report\''), 'Must indicate JSON loading progress')
  })

  it('dashboard-view.tsx implements downloadReport with dynamic filename creation', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('async function downloadReport('), 'downloadReport must be implemented')
    assert(dashboardViewCode.includes('incidentsApi.downloadReport(id, format)'), 'Must call incidentsApi.downloadReport')
    assert(dashboardViewCode.includes('${id}-report.${format}'), 'Must format filename with incident ID and extension')
    assert(dashboardViewCode.includes('URL.createObjectURL(blob)'), 'Must create blob object URL for browser download')
    assert(dashboardViewCode.includes('URL.revokeObjectURL(fileUrl)'), 'Must revoke object URL after download to prevent memory leaks')
  })

  it('downloadReport provides contextual error handling when download fails', () => {
    const dashboardViewCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/dashboard-view.tsx'), 'utf8')
    assert(dashboardViewCode.includes('Could not download ${format.toUpperCase()} report'), 'Must handle download error with dedicated title')
    assert(dashboardViewCode.includes('error instanceof Error ? error.message :'), 'Must display actual server error message in dialog')
  })
})
