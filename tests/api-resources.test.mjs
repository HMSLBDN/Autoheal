import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('AutoHeal DevOps — API Resources & Client Validation', () => {
  const rootDir = process.cwd()

  it('lib/api/resources.ts defines all required resource APIs', () => {
    const resourcesCode = fs.readFileSync(path.join(rootDir, 'lib/api/resources.ts'), 'utf8')
    assert(resourcesCode.includes('export const healthApi ='), 'healthApi must be exported')
    assert(resourcesCode.includes('export const servicesApi ='), 'servicesApi must be exported')
    assert(resourcesCode.includes('export const incidentsApi ='), 'incidentsApi must be exported')
    assert(resourcesCode.includes('export const recoveriesApi ='), 'recoveriesApi must be exported')
    assert(resourcesCode.includes('export const analyticsApi ='), 'analyticsApi must be exported')
    assert(resourcesCode.includes('export const settingsApi ='), 'settingsApi must be exported')
  })

  it('recoveriesApi.reject supports optional reason and validates signature', () => {
    const resourcesCode = fs.readFileSync(path.join(rootDir, 'lib/api/resources.ts'), 'utf8')
    assert(resourcesCode.includes('async reject(id: string, reason?: string)'), 'reject must accept id and optional reason')
    assert(resourcesCode.includes("`/api/v1/recoveries/${encodeURIComponent(id)}/reject`"), 'reject must use correct endpoint path')
    assert(resourcesCode.includes('body: JSON.stringify({ reason })'), 'reject must send reason payload')
  })

  it('incidentsApi.downloadReport supports pdf and json formats', () => {
    const resourcesCode = fs.readFileSync(path.join(rootDir, 'lib/api/resources.ts'), 'utf8')
    assert(resourcesCode.includes("async downloadReport(id: string, format: 'pdf' | 'json' = 'pdf'"), 'downloadReport must accept format with default pdf')
    assert(resourcesCode.includes("apiBlob(`/api/v1/incidents/${encodeURIComponent(id)}/report?format=${format}`"), 'downloadReport must call /report?format=')
  })

  it('validateRecovery strictly validates status, verification, and evidence classification', () => {
    const resourcesCode = fs.readFileSync(path.join(rootDir, 'lib/api/resources.ts'), 'utf8')
    assert(resourcesCode.includes("'pending_approval', 'approved', 'running', 'completed', 'failed', 'rejected'"), 'validateRecovery must enforce valid statuses')
    assert(resourcesCode.includes("'pending', 'passed', 'failed', 'not_started'"), 'validateRecovery must enforce valid verification states')
    assert(resourcesCode.includes("'SIMULATED', 'DOCKER_API_ACCEPTED', 'HEALTH_VERIFIED', 'VERIFICATION_FAILED'"), 'validateRecovery must support all evidence classifications')
  })

  it('validateIncident strictly validates severity and lifecycle statuses', () => {
    const resourcesCode = fs.readFileSync(path.join(rootDir, 'lib/api/resources.ts'), 'utf8')
    assert(resourcesCode.includes("'critical', 'high', 'medium', 'low'"), 'validateIncident must check severities')
    assert(resourcesCode.includes("'open', 'investigating', 'recovering', 'resolved'"), 'validateIncident must check statuses')
    assert(resourcesCode.includes('validateEvidence'), 'validateIncident must validate evidence array')
    assert(resourcesCode.includes('validateEvent'), 'validateIncident must validate events array')
  })

  it('lib/api/client.ts implements Refresh Token Rotation (RTR) lock and auth headers', () => {
    const clientCode = fs.readFileSync(path.join(rootDir, 'lib/api/client.ts'), 'utf8')
    assert(clientCode.includes('activeRefreshPromise'), 'client.ts must deduplicate concurrent refresh calls via RTR lock')
    assert(clientCode.includes('/api/v1/auth/refresh'), 'client.ts must refresh against /api/v1/auth/refresh')
    assert(clientCode.includes('Bearer'), 'client.ts must inject Authorization: Bearer token header')
    assert(clientCode.includes('credentials: \'include\''), 'client.ts must include HTTP-only credentials')
  })
})
