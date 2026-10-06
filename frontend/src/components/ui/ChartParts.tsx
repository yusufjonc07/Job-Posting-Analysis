// Chart chrome shared by every chart: glass tooltip box, legend, axis styling and the split bar.
import clsx from 'clsx'
import type { ReactNode } from 'react'
import { AXIS, GRID, MUTED } from '../../lib/palette'

export interface TooltipRow {
  key: string
  label: ReactNode
  value: ReactNode
  color?: string
  /** 'line' draws a short line key instead of a square swatch. */
  kind?: 'square' | 'line'
}

/** The floating glass tooltip used by recharts `content` and the custom SVG charts. */
export function TooltipBox({ title, rows, footer }: { title?: ReactNode; rows: TooltipRow[]; footer?: ReactNode }) {
  return (
    <div className="glass-strong pointer-events-none min-w-36 rounded-xl px-3 py-2 text-xs text-slate-700">
      {title !== undefined && <div className="mb-1 font-semibold text-slate-900">{title}</div>}
      <div className="space-y-0.5">
        {rows.map((r) => (
          <div key={r.key} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5">
              {r.color && <Swatch color={r.color} kind={r.kind} />}
              {r.label}
            </span>
            <span className="font-medium text-slate-900 tabular-nums">{r.value}</span>
          </div>
        ))}
      </div>
      {footer !== undefined && <div className="mt-1.5 border-t border-slate-200/80 pt-1.5 text-slate-500">{footer}</div>}
    </div>
  )
}

export function Swatch({ color, kind = 'square' }: { color: string; kind?: 'square' | 'line' }) {
  return (
    <span
      aria-hidden
      className={clsx('inline-block shrink-0', kind === 'line' ? 'h-0.5 w-3 rounded-full' : 'size-2.5 rounded-[3px]')}
      style={{ backgroundColor: color }}
    />
  )
}

export function Legend({ items, className }: { items: { key: string; label: ReactNode; color: string; kind?: 'square' | 'line' }[]; className?: string }) {
  return (
    <ul className={clsx('flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600', className)}>
      {items.map((i) => (
        <li key={i.key} className="flex items-center gap-1.5">
          <Swatch color={i.color} kind={i.kind} />
          {i.label}
        </li>
      ))}
    </ul>
  )
}

/** Recharts axis props: muted 11 px ticks, hairline axis, no tick marks. */
export const axisProps = {
  tick: { fill: MUTED, fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: AXIS },
} as const

export const yAxisProps = { ...axisProps, axisLine: false, width: 48 } as const

/** Recharts grid: horizontal solid hairlines only. */
export const gridProps = { stroke: GRID, vertical: false } as const

/** One horizontal bar split into segments (2 px surface gaps), e.g. location sources. */
export function SplitBar({ parts, height = 12 }: { parts: { key: string; value: number; color: string; label: string }[]; height?: number }) {
  const total = parts.reduce((s, p) => s + p.value, 0)
  return (
    <div className="flex w-full gap-0.5 overflow-hidden rounded-[4px]" style={{ height }} role="img" aria-label={parts.map((p) => `${p.label} ${p.value}`).join(', ')}>
      {total > 0 &&
        parts
          .filter((p) => p.value > 0)
          .map((p) => <div key={p.key} title={p.label} style={{ flexGrow: p.value, flexBasis: 0, backgroundColor: p.color, minWidth: 2 }} />)}
      {total === 0 && <div className="w-full bg-slate-900/[0.05]" />}
    </div>
  )
}
