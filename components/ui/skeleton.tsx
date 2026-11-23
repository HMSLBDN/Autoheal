import { cn } from '@/lib/utils'

export function Skeleton({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn('skeleton-shimmer', className)}
      aria-hidden="true"
      {...props}
    />
  )
}

export function MetricCardSkeleton({ tone = 'teal' }: { tone?: 'teal' | 'violet' | 'amber' }) {
  return (
    <article className="dash-card metric-card" role="status" aria-label="Loading metric...">
      <div className="metric-top">
        <Skeleton className="h-3 w-20" />
        <span className={`metric-icon ${tone}`}>
          <Skeleton className="h-3 w-3 rounded-full" />
        </span>
      </div>
      <div className="mt-2.5">
        <Skeleton className="h-7 w-24" />
      </div>
      <div className="metric-foot mt-2">
        <Skeleton className="h-2.5 w-28" />
        <Skeleton className="h-2 w-2 rounded-full" />
      </div>
    </article>
  )
}

export function TableSkeleton({
  columns = 5,
  rows = 5,
  hasHeader = true,
}: {
  columns?: number
  rows?: number
  hasHeader?: boolean
}) {
  return (
    <div className="data-table-wrap" role="status" aria-label="Loading table data...">
      <table className="data-table">
        {hasHeader && (
          <thead>
            <tr>
              {Array.from({ length: columns }).map((_, i) => (
                <th key={`th-${i}`}>
                  <Skeleton className="h-3 w-16" />
                </th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {Array.from({ length: rows }).map((_, r) => (
            <tr key={`tr-${r}`}>
              {Array.from({ length: columns }).map((_, c) => (
                <td key={`td-${r}-${c}`}>
                  {c === 0 ? (
                    <div style={{ display: 'grid', gap: 4 }}>
                      <Skeleton className="h-3.5 w-28" />
                      <Skeleton className="h-2 w-16" />
                    </div>
                  ) : c === 2 ? (
                    <Skeleton className="h-5 w-16 rounded-full" />
                  ) : (
                    <Skeleton className="h-3 w-20" />
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ChartSkeleton({
  height = 210,
  title,
  subtitle,
}: {
  height?: number
  title?: string
  subtitle?: string
}) {
  return (
    <div role="status" aria-label="Loading chart data..." style={{ width: '100%' }}>
      {(title || subtitle) && (
        <div style={{ marginBottom: 12, display: 'grid', gap: 4 }}>
          {title ? (
            <h2 className="panel-title">{title}</h2>
          ) : (
            <Skeleton className="h-3.5 w-32" />
          )}
          {subtitle ? (
            <p className="panel-subtitle">{subtitle}</p>
          ) : (
            <Skeleton className="h-2.5 w-48" />
          )}
        </div>
      )}
      <div
        style={{
          height,
          width: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '12px 6px 0',
          background: 'rgba(17, 24, 39, 0.4)',
          borderRadius: 8,
          border: '1px solid rgba(148, 163, 184, 0.08)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'flex-end', height: '80%', gap: 12 }}>
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={`bar-${i}`}
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'flex-end',
                height: '100%',
              }}
            >
              <Skeleton
                className="w-full"
                style={{
                  height: `${25 + (i * 13) % 65}%`,
                  borderRadius: '4px 4px 0 0',
                }}
              />
            </div>
          ))}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0 2px' }}>
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={`lbl-${i}`} className="h-2 w-7" />
          ))}
        </div>
      </div>
    </div>
  )
}

export function ListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div className="activity-list" role="status" aria-label="Loading activity...">
      {Array.from({ length: count }).map((_, i) => (
        <div className="activity-item" key={`item-${i}`}>
          <Skeleton className="h-3 w-3 rounded-full shrink-0" style={{ marginTop: 2 }} />
          <div className="activity-text" style={{ flex: 1, display: 'grid', gap: 4 }}>
            <Skeleton className="h-3 w-36" />
            <Skeleton className="h-2.5 w-48" />
            <Skeleton className="h-2 w-24" />
          </div>
        </div>
      ))}
    </div>
  )
}
