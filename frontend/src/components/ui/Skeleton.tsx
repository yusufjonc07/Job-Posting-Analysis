// Loading placeholders: Skeleton block, SkeletonText lines and ChartSkeleton (first load only, never on refetch).
import clsx from 'clsx'

/** A pulsing block; size it with className (e.g. "h-4 w-32"). */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={clsx('animate-pulse rounded-lg bg-slate-300/35', className)} />
}

/** A few lines of text-shaped skeletons. */
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden className={clsx('space-y-2', className)}>
      {Array.from({ length: lines }, (_, i) => (
        <Skeleton key={i} className={clsx('h-3', i === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  )
}

/** Chart-shaped skeleton: rising columns over a baseline; `height` in px includes the axis band. */
export function ChartSkeleton({ height = 240, className }: { height?: number; className?: string }) {
  const bars = [38, 52, 44, 63, 58, 71, 66, 80, 74, 88, 70, 92]
  return (
    <div aria-hidden className={clsx('flex flex-col', className)} style={{ height }}>
      <div className="flex flex-1 items-end gap-2 border-b border-slate-200/80 px-1">
        {bars.map((h, i) => (
          <div key={i} className="flex-1 animate-pulse rounded-t-[4px] bg-slate-300/30" style={{ height: `${h}%` }} />
        ))}
      </div>
      <div className="mt-2 flex justify-between px-1">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-2.5 w-10" />
        ))}
      </div>
    </div>
  )
}
