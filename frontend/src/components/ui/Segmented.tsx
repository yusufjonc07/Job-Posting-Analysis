// Segmented control (radio group of pill buttons), e.g. the 7d / 30d / 90d / 1y / All period picker.
import clsx from 'clsx'
import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

export interface SegmentedOption<T extends string> {
  value: T
  label: ReactNode
  icon?: LucideIcon
  title?: string
}

export interface SegmentedProps<T extends string> {
  options: SegmentedOption<T>[]
  /** Selected value; undefined/unknown selects nothing. */
  value: T | undefined
  onChange: (value: T) => void
  ariaLabel: string
  size?: 'sm' | 'md'
  className?: string
}

export function Segmented<T extends string>({ options, value, onChange, ariaLabel, size = 'md', className }: SegmentedProps<T>) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className={clsx(
        'inline-flex items-center gap-0.5 rounded-xl bg-slate-900/[0.05] p-0.5 ring-1 ring-inset ring-slate-900/[0.04]',
        className,
      )}
    >
      {options.map((o) => {
        const active = o.value === value
        const Icon = o.icon
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={active}
            title={o.title}
            onClick={() => onChange(o.value)}
            className={clsx(
              'inline-flex items-center justify-center gap-1.5 rounded-[10px] font-medium whitespace-nowrap transition-colors',
              size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-8 px-3 text-[13px]',
              active
                ? 'bg-white text-blue-700 shadow-sm ring-1 ring-slate-900/[0.06]'
                : 'text-slate-600 hover:bg-white/50 hover:text-slate-900',
            )}
          >
            {Icon && <Icon className={size === 'sm' ? 'size-3.5' : 'size-4'} aria-hidden />}
            {o.label}
          </button>
        )
      })}
    </div>
  )
}
