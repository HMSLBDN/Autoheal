'use client'

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type {
  DetectionLatencyPoint,
  ErrorRatePoint,
  RecoveryDurationPoint,
  RecoverySuccessPoint,
} from '@/types'

export type {
  DetectionLatencyPoint,
  ErrorRatePoint,
  RecoveryDurationPoint,
  RecoverySuccessPoint,
}

const sharedTooltip = {
  contentStyle: { background: '#111827', border: '1px solid rgba(148,163,184,.18)', borderRadius: 9, color: '#e2e8f0', fontSize: 10 },
  itemStyle: { color: '#35d6c5' },
  labelStyle: { color: '#94a3b8', marginBottom: 4 },
}

export function IncidentAreaChart({ data, compact = false }: { data: Array<{ date: string; incidents: number; recoveries: number }>; compact?: boolean }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: compact ? -24 : -18 }}>
        <defs>
          <linearGradient id="incidentFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#35d6c5" stopOpacity={.2} /><stop offset="95%" stopColor="#35d6c5" stopOpacity={0} /></linearGradient>
          <linearGradient id="recoveryFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8b7cff" stopOpacity={.17} /><stop offset="95%" stopColor="#8b7cff" stopOpacity={0} /></linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(148,163,184,.1)" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} tickMargin={9} />
        <YAxis hide={compact} tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} />
        <Tooltip {...sharedTooltip} />
        <Area type="monotone" dataKey="incidents" name="Incidents" stroke="#35d6c5" strokeWidth={2} fill="url(#incidentFill)" />
        <Area type="monotone" dataKey="recoveries" name="Recoveries" stroke="#8b7cff" strokeWidth={1.5} fill="url(#recoveryFill)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function AvailabilityChart({ data, compact = false }: { data: Array<{ date: string; availability: number }>; compact?: boolean }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 4, bottom: 0, left: compact ? -26 : -20 }}>
        <defs><linearGradient id="availabilityFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#35d6c5" stopOpacity={.23} /><stop offset="95%" stopColor="#35d6c5" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="rgba(148,163,184,.1)" vertical={false} />
        <XAxis dataKey="date" tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} tickMargin={9} />
        {!compact && <YAxis domain={[99.5, 100]} tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} width={35} />}
        <Tooltip {...sharedTooltip} />
        <Area type="monotone" dataKey="availability" name="Availability %" stroke="#35d6c5" strokeWidth={2} fill="url(#availabilityFill)" />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function MiniTrend({ color = '#35d6c5' }: { color?: string }) {
  const data = [{ n: 1, v: 22 }, { n: 2, v: 18 }, { n: 3, v: 27 }, { n: 4, v: 21 }, { n: 5, v: 32 }, { n: 6, v: 25 }, { n: 7, v: 38 }, { n: 8, v: 31 }, { n: 9, v: 43 }]
  return <ResponsiveContainer width="100%" height="100%"><AreaChart data={data}><defs><linearGradient id="miniFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={color} stopOpacity={.23} /><stop offset="100%" stopColor={color} stopOpacity={0} /></linearGradient></defs><Area dataKey="v" type="monotone" stroke={color} strokeWidth={1.7} fill="url(#miniFill)" /></AreaChart></ResponsiveContainer>
}

export function DetectionLatencyChart({
  data,
  compact = false,
  targetSeconds = 60,
  averageSeconds,
}: {
  data: DetectionLatencyPoint[]
  compact?: boolean
  targetSeconds?: number
  averageSeconds?: number
}) {
  const hasValidPoints = data.some((d) => typeof d.latencySeconds === 'number' && Number.isFinite(d.latencySeconds))

  return (
    <div style={{ position: 'relative', width: '100%', height: '100%' }}>
      {!hasValidPoints && averageSeconds !== undefined && (
        <div
          style={{
            position: 'absolute',
            top: 4,
            right: 6,
            zIndex: 10,
            background: 'rgba(15, 23, 42, 0.9)',
            border: '1px solid rgba(245, 179, 75, 0.35)',
            borderRadius: 6,
            padding: '2px 8px',
            fontSize: 9,
            color: '#f5b34b',
            letterSpacing: '0.01em',
          }}
        >
          Daily series unavailable · Org average: {averageSeconds}s
        </div>
      )}
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: compact ? -24 : -18 }}>
          <defs>
            <linearGradient id="latencyFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#35d6c5" stopOpacity={0.22} />
              <stop offset="95%" stopColor="#35d6c5" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="rgba(148,163,184,.1)" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} tickMargin={9} />
          <YAxis hide={compact} tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} unit="s" />
          <Tooltip
            {...sharedTooltip}
            formatter={(value: unknown) => [
              value === null || value === undefined ? 'Unavailable (No daily sample recorded)' : `${value}s`,
              'Detection Latency',
            ]}
          />
          {targetSeconds !== undefined && (
            <ReferenceLine
              y={targetSeconds}
              stroke="#f5b34b"
              strokeDasharray="3 3"
              label={{ value: `Target (${targetSeconds}s)`, fill: '#f5b34b', fontSize: 9, position: 'insideTopRight' }}
            />
          )}
          {averageSeconds !== undefined && (
            <ReferenceLine
              y={averageSeconds}
              stroke="#35d6c5"
              strokeDasharray="4 2"
              label={{ value: `Avg (${averageSeconds}s)`, fill: '#35d6c5', fontSize: 9, position: 'insideBottomRight' }}
            />
          )}
          <Area
            type="monotone"
            dataKey="latencySeconds"
            name="Detection Latency"
            stroke="#35d6c5"
            strokeWidth={2}
            fill="url(#latencyFill)"
            connectNulls={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

export function RecoveryDurationChart({
  data,
  compact = false,
  meanDurationMinutes,
}: {
  data: RecoveryDurationPoint[]
  compact?: boolean
  meanDurationMinutes?: number
}) {
  const meanSeconds = meanDurationMinutes !== undefined ? Math.round(meanDurationMinutes * 60) : undefined

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: compact ? -24 : -18 }}>
        <CartesianGrid stroke="rgba(148,163,184,.1)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: '#78869a', fontSize: 9 }}
          axisLine={false}
          tickLine={false}
          tickMargin={9}
        />
        <YAxis hide={compact} tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} unit="s" />
        <Tooltip
          {...sharedTooltip}
          formatter={(value: unknown, _name: unknown, item: { payload?: RecoveryDurationPoint }) => {
            if (value === null || value === undefined) {
              return ['Unavailable / Not executed', 'Recovery Duration']
            }
            const sec = Number(value)
            const min = (sec / 60).toFixed(1)
            const service = item?.payload?.serviceName ? ` · ${item.payload.serviceName}` : ''
            const action = item?.payload?.action ? ` (${item.payload.action})` : ''
            return [`${sec}s (${min} min)${service}${action}`, 'Duration']
          }}
        />
        {meanSeconds !== undefined && (
          <ReferenceLine
            y={meanSeconds}
            stroke="#8b7cff"
            strokeDasharray="3 3"
            label={{ value: `Mean (${meanDurationMinutes}m)`, fill: '#8b7cff', fontSize: 9, position: 'insideTopRight' }}
          />
        )}
        <Bar dataKey="durationSeconds" name="Duration (s)" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => {
            const isFailed = entry.status === 'failed' || entry.verification === 'failed'
            const isRejected = entry.status === 'rejected'
            const color = isFailed ? '#f43f5e' : isRejected ? '#78869a' : '#8b7cff'
            return <Cell key={`rec-dur-cell-${index}`} fill={color} />
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function ErrorRateChart({
  data,
  compact = false,
  criticalThreshold = 1.0,
}: {
  data: ErrorRatePoint[]
  compact?: boolean
  criticalThreshold?: number
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: compact ? -24 : -18 }}>
        <CartesianGrid stroke="rgba(148,163,184,.1)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: '#78869a', fontSize: 9 }}
          axisLine={false}
          tickLine={false}
          tickMargin={9}
        />
        <YAxis hide={compact} tick={{ fill: '#78869a', fontSize: 9 }} axisLine={false} tickLine={false} unit="%" />
        <Tooltip
          {...sharedTooltip}
          formatter={(value: unknown, _name: unknown, item: { payload?: ErrorRatePoint }) => [
            value === null || value === undefined
              ? 'Unavailable'
              : `${Number(value).toFixed(2)}%${item?.payload?.status ? ` (${item.payload.status})` : ''}`,
            'Error Rate',
          ]}
        />
        <ReferenceLine
          y={criticalThreshold}
          stroke="#f43f5e"
          strokeDasharray="3 3"
          label={{ value: `Threshold (${criticalThreshold}%)`, fill: '#f43f5e', fontSize: 9, position: 'insideTopRight' }}
        />
        <Bar dataKey="errorRate" name="Error Rate %" radius={[4, 4, 0, 0]}>
          {data.map((entry, index) => {
            const val = entry.errorRate ?? 0
            const thresh = entry.threshold ?? criticalThreshold
            const color = val > thresh ? '#f43f5e' : val >= thresh * 0.5 ? '#f5b34b' : '#35d6c5'
            return <Cell key={`err-rate-cell-${index}`} fill={color} />
          })}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

export function RecoverySuccessRateChart({
  data,
  compact = false,
  targetRate = 95,
  overallRate,
}: {
  data: RecoverySuccessPoint[]
  compact?: boolean
  targetRate?: number
  overallRate?: number
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: compact ? -24 : -18 }}>
        <defs>
          <linearGradient id="successFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#35d6c5" stopOpacity={0.22} />
            <stop offset="95%" stopColor="#35d6c5" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="rgba(148,163,184,.1)" vertical={false} />
        <XAxis
          dataKey="label"
          tick={{ fill: '#78869a', fontSize: 9 }}
          axisLine={false}
          tickLine={false}
          tickMargin={9}
        />
        <YAxis
          hide={compact}
          domain={[0, 100]}
          tick={{ fill: '#78869a', fontSize: 9 }}
          axisLine={false}
          tickLine={false}
          unit="%"
        />
        <Tooltip
          {...sharedTooltip}
          formatter={(value: unknown, _name: unknown, item: { payload?: RecoverySuccessPoint }) => {
            if (value === null || value === undefined) {
              return ['Unavailable / No operations in period', 'Success Rate']
            }
            const ops =
              item?.payload?.totalOperations !== undefined
                ? ` (${item.payload.successfulOperations ?? '?'}/${item.payload.totalOperations} ops)`
                : ''
            return [`${Number(value).toFixed(1)}%${ops}`, 'Success Rate']
          }}
        />
        {targetRate !== undefined && (
          <ReferenceLine
            y={targetRate}
            stroke="#35d6c5"
            strokeDasharray="3 3"
            label={{ value: `Target (${targetRate}%)`, fill: '#35d6c5', fontSize: 9, position: 'insideTopRight' }}
          />
        )}
        {overallRate !== undefined && (
          <ReferenceLine
            y={overallRate}
            stroke="#8b7cff"
            strokeDasharray="4 2"
            label={{ value: `Overall (${overallRate}%)`, fill: '#8b7cff', fontSize: 9, position: 'insideBottomRight' }}
          />
        )}
        <Area
          type="monotone"
          dataKey="successRate"
          name="Recovery Success Rate"
          stroke="#35d6c5"
          strokeWidth={2}
          fill="url(#successFill)"
          connectNulls={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
