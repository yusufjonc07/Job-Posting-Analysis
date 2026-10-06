// Styled native <select> with a chevron; generic over the option value type.
import clsx from 'clsx'
import { ChevronDown, type LucideIcon } from 'lucide-react'

export interface SelectOption<T extends string> {
  value: T
  label: string
}

export interface SelectProps<T extends string> {
  value: T
  onChange: (value: T) => void
  options: SelectOption<T>[]
  ariaLabel: string
  icon?: LucideIcon
  size?: 'sm' | 'md'
  className?: string
}

export function Select<T extends string>({ value, onChange, options, ariaLabel, icon: Icon, size = 'md', className }: SelectProps<T>) {
  return (
    <div className={clsx('relative inline-flex items-center', className)}>
      {Icon && <Icon className="pointer-events-none absolute left-2.5 size-4 text-slate-500" aria-hidden />}
      <select
        aria-label={ariaLabel}
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        className={clsx(
          'w-full cursor-pointer appearance-none rounded-xl bg-white/70 font-medium text-slate-700 shadow-sm ring-1 ring-slate-900/[0.08] transition-colors ring-inset hover:bg-white hover:text-slate-900 focus-visible:outline-2 focus-visible:outline-blue-500',
          size === 'sm' ? 'h-7 pr-7 text-xs' : 'h-9 pr-8 text-[13px]',
          Icon ? 'pl-8' : size === 'sm' ? 'pl-2.5' : 'pl-3',
        )}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-2.5 size-4 text-slate-500" aria-hidden />
    </div>
  )
}
