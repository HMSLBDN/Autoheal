import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('AutoHeal DevOps — Frontend/Backend API Contract Verification', () => {
  const rootDir = process.cwd()

  it('Service contract matches frontend Service interface', () => {
    const serviceSchema = fs.readFileSync(path.join(rootDir, 'backend/app/schemas/service.py'), 'utf8')
    assert(serviceSchema.includes('availability: float'), 'Service schema must include availability float')
    assert(serviceSchema.includes('error_rate: float'), 'Service schema must include error_rate float')
    assert(serviceSchema.includes('latency_ms: int'), 'Service schema must include latency_ms int')
    assert(serviceSchema.includes('serialization_alias="errorRate"'), 'Backend must serialize errorRate camelCase')
    assert(serviceSchema.includes('serialization_alias="latencyMs"'), 'Backend must serialize latencyMs camelCase')
    assert(serviceSchema.includes('serialization_alias="lastChecked"'), 'Backend must serialize lastChecked camelCase')
  })

  it('Incident contract matches frontend Incident interface', () => {
    const incidentSchema = fs.readFileSync(path.join(rootDir, 'backend/app/schemas/incident.py'), 'utf8')
    assert(incidentSchema.includes('serialization_alias="serviceId"'), 'Backend must serialize serviceId camelCase')
    assert(incidentSchema.includes('serialization_alias="serviceName"'), 'Backend must serialize serviceName camelCase')
    assert(incidentSchema.includes('serialization_alias="detectedAt"'), 'Backend must serialize detectedAt camelCase')
    assert(incidentSchema.includes('serialization_alias="recoveryStatus"'), 'Backend must serialize recoveryStatus camelCase')
    assert(incidentSchema.includes('serialization_alias="probableCause"'), 'Backend must serialize probableCause camelCase')
    assert(incidentSchema.includes('serialization_alias="recommendedAction"'), 'Backend must serialize recommendedAction camelCase')
    assert(incidentSchema.includes('evidence: List[IncidentEvidenceResponse]'), 'Backend must serialize evidence array')
    assert(incidentSchema.includes('events: List[IncidentEventResponse]'), 'Backend must serialize events array')
  })

  it('RecoveryAction contract matches frontend RecoveryAction and RecoveryResult interfaces', () => {
    const recoverySchema = fs.readFileSync(path.join(rootDir, 'backend/app/schemas/recovery.py'), 'utf8')
    assert(recoverySchema.includes('serialization_alias="incidentId"'), 'Recovery schema must serialize incidentId')
    assert(recoverySchema.includes('serialization_alias="serviceName"'), 'Recovery schema must serialize serviceName')
    assert(recoverySchema.includes('serialization_alias="approvalRequired"'), 'Recovery schema must serialize approvalRequired')
    assert(recoverySchema.includes('serialization_alias="requestedBy"'), 'Recovery schema must serialize requestedBy')
    assert(recoverySchema.includes('serialization_alias="requestedAt"'), 'Recovery schema must serialize requestedAt')
    assert(recoverySchema.includes('serialization_alias="durationSeconds"'), 'Recovery schema must serialize durationSeconds')
    assert(recoverySchema.includes('serialization_alias="executionMode"'), 'Recovery schema must serialize executionMode')
    assert(recoverySchema.includes('serialization_alias="evidenceClassification"'), 'Recovery schema must serialize evidenceClassification')
    assert(recoverySchema.includes('serialization_alias="completedAt"'), 'RecoveryResult must serialize completedAt')
    assert(recoverySchema.includes('serialization_alias="diagnosticOutput"'), 'RecoveryResult must serialize diagnosticOutput')
  })

  it('Analytics contract matches frontend AnalyticsSummary interface', () => {
    const analyticsSchema = fs.readFileSync(path.join(rootDir, 'backend/app/schemas/analytics.py'), 'utf8')
    assert(analyticsSchema.includes('serialization_alias="detectionLatencySeconds"'), 'Analytics must serialize detectionLatencySeconds')
    assert(analyticsSchema.includes('serialization_alias="recoveryDurationMinutes"'), 'Analytics must serialize recoveryDurationMinutes')
    assert(analyticsSchema.includes('serialization_alias="recoverySuccessRate"'), 'Analytics must serialize recoverySuccessRate')
    assert(analyticsSchema.includes('serialization_alias="falsePositiveRate"'), 'Analytics must serialize falsePositiveRate')
    assert(analyticsSchema.includes('serialization_alias="incidentCount"'), 'Analytics must serialize incidentCount')
  })

  it('Report endpoint formats match frontend download expectations', () => {
    const incidentsRoute = fs.readFileSync(path.join(rootDir, 'backend/app/api/routes/incidents.py'), 'utf8')
    assert(incidentsRoute.includes('format: Optional[str] = Query("pdf"'), 'Report endpoint must accept format query param')
    assert(incidentsRoute.includes('media_type="application/pdf"'), 'Report endpoint must return application/pdf')
    assert(incidentsRoute.includes('media_type="application/json"'), 'Report endpoint must return application/json')
    assert(incidentsRoute.includes('Content-Disposition'), 'Report endpoint must set attachment content-disposition header')
  })
})
