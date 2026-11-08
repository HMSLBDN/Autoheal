'use client'

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

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
