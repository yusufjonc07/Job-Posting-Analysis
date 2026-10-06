// Small pill label with tones and an optional colour dot (e.g. visa chips, "Forwarded", "Nationwide").
import clsx from 'clsx'
import type { ReactNode } from 'react'

export type BadgeTone = 'neutral' | 'blue' | 'indigo' | 'orange' | 'aqua' | 'amber' | 'green' | 'red'

const TONES: Record<BadgeTone, string> = {
  neutral: 'bg-slate-500/10 text-slate-700 ring-slate-500/15',
  blue: 'bg-blue-500/10 text-blue-700 ring-blue-600/15',
  indigo: 'bg-indigo-500/10 text-indigo-700 ring-indigo-600/15',
  orange: 'bg-orange-500/10 text-orange-800 ring-orange-600/15',
  aqua: 'bg-emerald-500/10 text-emerald-800 ring-emerald-600/15',
  amber: 'bg-amber-400/15 text-amber-800 ring-amber-600/20',
  green: 'bg-green-500/10 text-green-800 ring-green-600/15',
  red: 'bg-rose-500/10 text-rose-700 ring-rose-600/15',
}

export interface BadgeProps {
  tone?: BadgeTone
  /** A leading dot; pass a colour (e.g. SERIES[1]) to key it to a chart series. */
  dot?: boolean | string
  title?: string
  className?: string
  children: ReactNode
}

export function Badge({ tone = 'neutral', dot, title, className, children }: BadgeProps) {
  return (
    <span
      title={title}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {dot && (
        <span
          aria-hidden
          className={clsx('size-1.5 rounded-full', typeof dot !== 'string' && 'bg-current')}
          style={typeof dot === 'string' ? { backgroundColor: dot } : undefined}
        />
      )}
      {children}
    </span>
  )
}
