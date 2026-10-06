// Live status pill: green pulsing "Live", amber "Reconnecting…", blue "Loading data 42%", red "Offline".
import clsx from 'clsx'
import { useLive, type LiveStatus } from '../../state/live'

const LOOK: Record<LiveStatus, { dot: string; ring: string; text: string; label: string }> = {
  live: { dot: 'bg-emerald-500', ring: 'bg-emerald-400', text: 'text-emerald-800 bg-emerald-500/10 ring-emerald-600/15', label: 'Live' },
  connecting: { dot: 'bg-slate-400', ring: '', text: 'text-slate-600 bg-slate-500/10 ring-slate-500/15', label: 'Connecting…' },
  reconnecting: { dot: 'bg-amber-500', ring: '', text: 'text-amber-800 bg-amber-400/15 ring-amber-600/20', label: 'Reconnecting…' },
  loading: { dot: 'bg-blue-500', ring: 'bg-blue-400', text: 'text-blue-800 bg-blue-500/10 ring-blue-600/15', label: 'Loading data' },
  offline: { dot: 'bg-rose-500', ring: '', text: 'text-rose-700 bg-rose-500/10 ring-rose-600/15', label: 'Offline' },
}

export function LiveBadge({ className }: { className?: string }) {
  const { status, progress } = useLive()
  const look = LOOK[status]
  return (
    <span
      role="status"
      className={clsx('inline-flex h-7 items-center gap-2 rounded-full px-2.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset', look.text, className)}
    >
      <span className="relative flex size-2">
        {look.ring && <span className={clsx('absolute inset-0 animate-pulse-ring rounded-full', look.ring)} />}
        <span className={clsx('relative size-2 rounded-full', look.dot)} />
      </span>
      {look.label}
      {status === 'loading' && progress !== null && <span className="tabular-nums">{Math.round(progress * 100)}%</span>}
    </span>
  )
}

/** Plain-language status for the sidebar footer. */
export function statusText(status: LiveStatus): string {
  return { live: 'Live — new posts appear automatically', connecting: 'Connecting…', reconnecting: 'Reconnecting…', loading: 'Loading data…', offline: 'Backend offline' }[status]
}
