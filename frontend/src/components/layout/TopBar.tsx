// Page title + one filter row (period, source, group-location fallback) + live badge; menu buttons below 1280 px.
import { Menu, PanelRight } from 'lucide-react'
import { useLocation } from 'react-router'
import { routeFor } from '../../lib/routes'
import { PERIOD_PRESETS, SOURCE_OPTIONS, useFilters } from '../../state/filters'
import type { SourceFilter } from '../../api/types'
import { Segmented } from '../ui/Segmented'
import { Select } from '../ui/Select'
import { Toggle } from '../ui/Toggle'
import { LiveBadge } from './LiveBadge'

const PERIOD_OPTIONS = PERIOD_PRESETS.map((p) => ({ value: p.days === undefined ? 'all' : String(p.days), label: p.label }))

function IconButton({ label, onClick, children }: { label: string; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      className="inline-flex size-9 shrink-0 items-center justify-center rounded-xl bg-white/70 text-slate-600 shadow-sm ring-1 ring-slate-900/[0.08] hover:text-slate-900"
    >
      {children}
    </button>
  )
}

export function TopBar({ onOpenNav, onOpenSide, sideLabel }: { onOpenNav?: () => void; onOpenSide?: () => void; sideLabel: string }) {
  const { pathname } = useLocation()
  const route = routeFor(pathname)
  const { filters, setDays, setSource, setFallback } = useFilters()
  const period = filters.days === undefined ? 'all' : String(filters.days)

  return (
    <header className="glass px-5 py-4">
      <div className="flex items-start gap-3">
        {onOpenNav && (
          <IconButton label="Open navigation" onClick={onOpenNav}>
            <Menu className="size-4" aria-hidden />
          </IconButton>
        )}
        <div className="min-w-0 flex-1">
          <h1 className="text-xl leading-7 font-semibold tracking-tight text-slate-900">{route.title}</h1>
          <p className="mt-0.5 text-[13px] text-slate-500">{route.subtitle}</p>
        </div>
        <LiveBadge className="mt-0.5" />
        {onOpenSide && (
          <IconButton label={sideLabel} onClick={onOpenSide}>
            <PanelRight className="size-4" aria-hidden />
          </IconButton>
        )}
      </div>
      <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2">
        <Segmented
          ariaLabel="Period"
          value={PERIOD_OPTIONS.some((o) => o.value === period) ? period : undefined}
          onChange={(v) => setDays(v === 'all' ? undefined : Number(v))}
          options={PERIOD_OPTIONS}
        />
        <Select<SourceFilter> ariaLabel="Source" value={filters.source} onChange={setSource} options={SOURCE_OPTIONS} className="w-44" />
        <Toggle
          checked={filters.basis === 'all'}
          onChange={setFallback}
          label="Group location fallback"
          title="On: an ad without a place in its text counts in its group's home province. Off: only places named in the post count."
        />
      </div>
    </header>
  )
}
