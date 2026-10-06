// Ranked horizontal bars: label and value on one line, a thin bar (rounded data end) beneath.
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { fmtInt } from '../../lib/format'
import { SERIES } from '../../lib/palette'

export interface BarListItem {
  key: string
  label: ReactNode
  value: number
  /** Text shown for the value (defaults to the formatted number). */
  display?: ReactNode
  sub?: ReactNode
  color?: string
  to?: string
  onClick?: () => void
  active?: boolean
}

export interface BarListProps {
  items: BarListItem[]
  /** Scale maximum (defaults to the largest value). */
  max?: number
  color?: string
  className?: string
}

export function BarList({ items, max, color = SERIES[0], className }: BarListProps) {
  const top = max ?? Math.max(1, ...items.map((i) => i.value))
  return (
    <ul className={className ?? 'space-y-2.5'}>
      {items.map((item) => {
        const body = (
          <>
            <div className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="min-w-0 truncate text-slate-700">{item.label}</span>
              <span className="shrink-0 font-medium text-slate-900 tabular-nums">{item.display ?? fmtInt(item.value)}</span>
            </div>
            <div className="mt-1 h-2 rounded-r-[4px] bg-slate-900/[0.04]">
              <div
                className="h-full rounded-r-[4px] transition-[width] duration-500"
                style={{ width: `${Math.max(item.value > 0 ? 0.6 : 0, (item.value / top) * 100)}%`, backgroundColor: item.color ?? color }}
              />
            </div>
            {item.sub !== undefined && <div className="mt-0.5 text-[11px] text-slate-500">{item.sub}</div>}
          </>
        )
        const rowClass = clsx(
          'block w-full rounded-lg px-1.5 py-1 text-left transition-colors',
          (item.to || item.onClick) && 'hover:bg-blue-500/[0.06]',
          item.active && 'bg-blue-600/10',
        )
        return (
          <li key={item.key}>
            {item.to ? (
              <Link to={item.to} className={rowClass}>
                {body}
              </Link>
            ) : item.onClick ? (
              <button type="button" onClick={item.onClick} className={rowClass}>
                {body}
              </button>
            ) : (
              <div className={rowClass}>{body}</div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
