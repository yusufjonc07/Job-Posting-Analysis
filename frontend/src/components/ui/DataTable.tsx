// Table with a sticky header and optional click-to-sort columns; also the "Table" view of every chart.
import clsx from 'clsx'
import { ArrowDown, ArrowUp, ArrowUpDown } from 'lucide-react'
import { useMemo, useState, type ReactNode } from 'react'

export interface Column<T> {
  key: string
  header: ReactNode
  /** Native tooltip on the header. */
  title?: string
  cell: (row: T) => ReactNode
  align?: 'left' | 'right'
  /** Makes the column sortable. */
  sortValue?: (row: T) => number | string | null
  className?: string
  headerClassName?: string
}

export interface DataTableProps<T> {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  initialSort?: { key: string; dir: 'asc' | 'desc' }
  onRowClick?: (row: T) => void
  empty?: ReactNode
  /** Tighter cell padding for wide tables. */
  dense?: boolean
  className?: string
}

export function DataTable<T>({ columns, rows, rowKey, initialSort, onRowClick, empty, dense, className }: DataTableProps<T>) {
  const pad = dense ? 'px-2 py-1.5' : 'px-3 py-2'
  const [sort, setSort] = useState(initialSort)
  const sorted = useMemo(() => {
    const column = columns.find((c) => c.key === sort?.key)
    if (!sort || !column?.sortValue) return rows
    const value = column.sortValue
    const sign = sort.dir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const x = value(a)
      const y = value(b)
      if (x === y) return 0
      if (x === null) return 1
      if (y === null) return -1
      return (x < y ? -1 : 1) * sign
    })
  }, [columns, rows, sort])

  const toggle = (key: string) =>
    setSort((s) => (s?.key === key ? { key, dir: s.dir === 'desc' ? 'asc' : 'desc' } : { key, dir: 'desc' }))

  return (
    <table className={clsx('w-full border-separate border-spacing-0 text-[13px]', className)}>
      <thead>
        <tr>
          {columns.map((c) => {
            const active = sort?.key === c.key
            const Icon = active ? (sort?.dir === 'asc' ? ArrowUp : ArrowDown) : ArrowUpDown
            return (
              <th
                key={c.key}
                scope="col"
                title={c.title}
                aria-sort={active ? (sort?.dir === 'asc' ? 'ascending' : 'descending') : undefined}
                className={clsx(
                  'sticky top-0 z-10 border-b border-slate-200 bg-white/90 text-xs font-medium whitespace-nowrap text-slate-500 backdrop-blur',
                  pad,
                  c.align === 'right' ? 'text-right' : 'text-left',
                  c.headerClassName,
                )}
              >
                {c.sortValue ? (
                  <button
                    type="button"
                    onClick={() => toggle(c.key)}
                    className={clsx(
                      'inline-flex items-center gap-1 hover:text-slate-900',
                      c.align === 'right' && 'flex-row-reverse',
                      active && 'text-slate-900',
                    )}
                  >
                    {c.header}
                    <Icon className={clsx('size-3', !active && 'opacity-40')} aria-hidden />
                  </button>
                ) : (
                  c.header
                )}
              </th>
            )
          })}
        </tr>
      </thead>
      <tbody>
        {sorted.map((row) => (
          <tr
            key={rowKey(row)}
            onClick={onRowClick ? () => onRowClick(row) : undefined}
            className={clsx('group', onRowClick && 'cursor-pointer')}
          >
            {columns.map((c) => (
              <td
                key={c.key}
                className={clsx(
                  'border-b border-slate-200/60 align-middle text-slate-700 group-last:border-b-0 group-hover:bg-blue-50/50',
                  pad,
                  c.align === 'right' && 'text-right tabular-nums',
                  c.className,
                )}
              >
                {c.cell(row)}
              </td>
            ))}
          </tr>
        ))}
        {sorted.length === 0 && (
          <tr>
            <td colSpan={columns.length} className="px-3 py-10 text-center text-slate-500">
              {empty ?? 'Nothing to show'}
            </td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
