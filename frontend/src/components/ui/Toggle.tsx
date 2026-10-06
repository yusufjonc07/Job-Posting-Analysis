// Switch with a label (role="switch"), e.g. the "Group location fallback" filter.
import clsx from 'clsx'
import type { ReactNode } from 'react'

export interface ToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  label: ReactNode
  /** Extra explanation shown as a native tooltip. */
  title?: string
  size?: 'sm' | 'md'
  className?: string
}

export function Toggle({ checked, onChange, label, title, size = 'md', className }: ToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      title={title}
      onClick={() => onChange(!checked)}
      className={clsx(
        'group inline-flex items-center gap-2 rounded-xl font-medium whitespace-nowrap text-slate-700 hover:text-slate-900',
        size === 'sm' ? 'text-xs' : 'text-[13px]',
        className,
      )}
    >
      <span
        aria-hidden
        className={clsx(
          'relative inline-flex shrink-0 items-center rounded-full transition-colors',
          size === 'sm' ? 'h-4 w-7' : 'h-5 w-9',
          checked ? 'bg-blue-600' : 'bg-slate-300 group-hover:bg-slate-400',
        )}
      >
        <span
          className={clsx(
            'absolute rounded-full bg-white shadow-sm transition-transform',
            size === 'sm' ? 'left-0.5 size-3' : 'left-0.5 size-4',
            checked && (size === 'sm' ? 'translate-x-3' : 'translate-x-4'),
          )}
        />
      </span>
      {label}
    </button>
  )
}
