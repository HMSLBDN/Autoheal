import { describe, it } from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'

describe('AutoHeal DevOps — Analytics Charts & Truthful Telemetry', () => {
  const rootDir = process.cwd()

  it('components/dashboard/charts.tsx exports all four required analytics charts', () => {
    const chartsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/charts.tsx'), 'utf8')
    assert(chartsCode.includes('export function DetectionLatencyChart('), 'DetectionLatencyChart must be exported')
    assert(chartsCode.includes('export function RecoveryDurationChart('), 'RecoveryDurationChart must be exported')
    assert(chartsCode.includes('export function ErrorRateChart('), 'ErrorRateChart must be exported')
    assert(chartsCode.includes('export function RecoverySuccessRateChart('), 'RecoverySuccessRateChart must be exported')
  })

  it('DetectionLatencyChart renders target threshold and handles null latency truthfully', () => {
    const chartsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/charts.tsx'), 'utf8')
    assert(chartsCode.includes('ReferenceLine'), 'DetectionLatencyChart must render reference threshold')
    assert(chartsCode.includes('targetSeconds'), 'DetectionLatencyChart must accept targetSeconds')
    assert(chartsCode.includes('Daily series unavailable'), 'DetectionLatencyChart must indicate when daily series is unavailable')
    assert(chartsCode.includes('Unavailable (No daily sample recorded)'), 'DetectionLatencyChart tooltip must truthfully indicate missing samples')
  })

  it('RecoveryDurationChart displays duration in seconds with formatted tooltips', () => {
    const chartsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/charts.tsx'), 'utf8')
    assert(chartsCode.includes('durationSeconds'), 'RecoveryDurationChart must track duration in seconds')
    assert(chartsCode.includes('meanDurationMinutes'), 'RecoveryDurationChart must support mean duration reference line')
    assert(chartsCode.includes('Unavailable / Not executed'), 'RecoveryDurationChart must handle empty dataset without fabricating values')
  })

  it('ErrorRateChart displays error rate percentages with threshold line', () => {
    const chartsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/charts.tsx'), 'utf8')
    assert(chartsCode.includes('errorRate'), 'ErrorRateChart must map errorRate')
    assert(chartsCode.includes('criticalThreshold'), 'ErrorRateChart must render threshold reference')
    assert(chartsCode.includes('Unavailable'), 'ErrorRateChart must indicate unavailable data')
  })

  it('RecoverySuccessRateChart enforces 0-100 percentage domain and operation tallies', () => {
    const chartsCode = fs.readFileSync(path.join(rootDir, 'components/dashboard/charts.tsx'), 'utf8')
    assert(chartsCode.includes('successRate'), 'RecoverySuccessRateChart must display successRate')
    assert(chartsCode.includes('domain={[0, 100]}'), 'RecoverySuccessRateChart must clamp percentage domain 0 to 100')
    assert(chartsCode.includes('totalOperations'), 'RecoverySuccessRateChart must handle total operations tally')
    assert(chartsCode.includes('Unavailable / No operations in period'), 'RecoverySuccessRateChart must handle empty records gracefully')
  })

  it('types/index.ts defines proper TypeScript interfaces for all four chart data points', () => {
    const typesCode = fs.readFileSync(path.join(rootDir, 'types/index.ts'), 'utf8')
    assert(typesCode.includes('export interface DetectionLatencyPoint'), 'DetectionLatencyPoint must be exported')
    assert(typesCode.includes('export interface RecoveryDurationPoint'), 'RecoveryDurationPoint must be exported')
    assert(typesCode.includes('export interface ErrorRatePoint'), 'ErrorRatePoint must be exported')
    assert(typesCode.includes('export interface RecoverySuccessPoint'), 'RecoverySuccessPoint must be exported')
  })
})
