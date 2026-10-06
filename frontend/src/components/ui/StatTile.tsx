// KPI tile: label, value (proportional figures), optional sublabel and a signed delta vs a named period.
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { fmtSignedPct } from '../../lib/format'
import { DELTA_BAD, DELTA_GOOD } from '../../lib/palette'

export interface StatTileProps {
  label: string
  value: ReactNode
  sub?: ReactNode
  /** Relative change (0.12 = +12%) and what it compares against. */
  delta?: { value: number | null; vs: string; upIsGood?: boolean }
  className?: string
}

export function StatTile({ label, value, sub, delta, className }: StatTileProps) {
  const d = delta?.value
  const good = d !== null && d !== undefined && d !== 0 ? (d > 0) === (delta?.upIsGood ?? true) : null
  return (
    <div className={clsx('glass min-w-0 px-4 py-3.5', className)}>
      <div className="truncate text-xs font-medium text-slate-500">{label}</div>
      <div className="mt-1 truncate text-[26px] leading-8 font-semibold tracking-tight text-slate-900">{value}</div>
      {(sub !== undefined || delta) && (
        <div className="mt-1 flex flex-wrap items-baseline gap-x-2 text-xs leading-5 text-slate-500">
          {delta && d !== null && d !== undefined && (
            <span className="font-medium" style={{ color: good === null ? undefined : good ? DELTA_GOOD : DELTA_BAD }}>
              {fmtSignedPct(d, 0)} <span className="font-normal text-slate-500">{delta.vs}</span>
            </span>
          )}
          {sub !== undefined && <span className="truncate">{sub}</span>}
        </div>
      )}
    </div>
  )
}
