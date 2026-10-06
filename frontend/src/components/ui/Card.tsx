// Glass card: title, subtitle, actions, an optional Chart / Table toggle (pass `table`) and the body.
import clsx from 'clsx'
import { ChartColumn, Table2 } from 'lucide-react'
import { useState, type ReactNode } from 'react'
import { Segmented } from './Segmented'

export interface CardProps {
  title?: ReactNode
  subtitle?: ReactNode
  actions?: ReactNode
  /** The same numbers as a table; adds a Chart / Table toggle to the header. */
  table?: ReactNode
  footer?: ReactNode
  /** Previous data shown while new data loads: dimmed, never replaced by a skeleton. */
  stale?: boolean
  className?: string
  bodyClassName?: string
  children: ReactNode
}

export function Card({ title, subtitle, actions, table, footer, stale, className, bodyClassName, children }: CardProps) {
  const [view, setView] = useState<'chart' | 'table'>('chart')
  const hasHeader = title !== undefined || actions !== undefined || table !== undefined
  return (
    <section className={clsx('glass flex min-w-0 flex-col p-5', className)}>
      {hasHeader && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="min-w-0">
            {title !== undefined && <h2 className="text-[15px] leading-6 font-semibold text-slate-900">{title}</h2>}
            {subtitle !== undefined && <p className="mt-0.5 text-[13px] leading-5 text-slate-500">{subtitle}</p>}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            {actions}
            {table !== undefined && (
              <Segmented
                size="sm"
                ariaLabel="Show as chart or table"
                value={view}
                onChange={setView}
                options={[
                  { value: 'chart', label: <span className="sr-only">Chart</span>, icon: ChartColumn, title: 'Chart' },
                  { value: 'table', label: <span className="sr-only">Table</span>, icon: Table2, title: 'Table' },
                ]}
              />
            )}
          </div>
        </header>
      )}
      <div className={clsx('min-w-0 flex-1 transition-opacity duration-200', stale && 'opacity-55', bodyClassName)}>
        {table !== undefined && view === 'table' ? (
          <div className="scroll-thin max-h-[440px] overflow-auto">{table}</div>
        ) : (
          children
        )}
      </div>
      {footer !== undefined && <footer className="mt-4 text-xs leading-5 text-slate-500">{footer}</footer>}
    </section>
  )
}
