// Global filters ({days, source, basis}) synced with the URL search params (?days=30&source=direct&basis=post).
import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router'
import type { BasisFilter, Filters, SourceFilter } from '../api/types'

/** Period presets of the top-bar segmented control (`days` undefined = all time). */
export const PERIOD_PRESETS: { label: string; days: number | undefined }[] = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
  { label: '1y', days: 365 },
  { label: 'All', days: undefined },
]

export const SOURCE_OPTIONS: { value: SourceFilter; label: string }[] = [
  { value: 'all', label: 'All sources' },
  { value: 'direct', label: 'Direct posts' },
  { value: 'forwarded', label: 'Forwarded (bot)' },
]

export const DEFAULT_FILTERS: Filters = { days: undefined, source: 'all', basis: 'all' }

/** Parses filters from search params, falling back to defaults on invalid values. */
export function parseFilters(sp: URLSearchParams): Filters {
  const d = Number(sp.get('days'))
  const days = Number.isInteger(d) && d >= 1 ? d : undefined
  const s = sp.get('source')
  const source: SourceFilter = s === 'direct' || s === 'forwarded' ? s : 'all'
  const basis: BasisFilter = sp.get('basis') === 'post' ? 'post' : 'all'
  return { days, source, basis }
}

export interface UseFilters {
  filters: Filters
  setDays: (days: number | undefined) => void
  setSource: (source: SourceFilter) => void
  setBasis: (basis: BasisFilter) => void
  /** Convenience for the "Group location fallback" toggle: on ⇔ basis 'all'. */
  setFallback: (on: boolean) => void
  reset: () => void
  /** True when any filter differs from the defaults. */
  isFiltered: boolean
}

/** Current filters + setters; other search params (e.g. ?region=) are preserved. */
export function useFilters(): UseFilters {
  const [sp, setSp] = useSearchParams()
  const days = sp.get('days')
  const source = sp.get('source')
  const basis = sp.get('basis')
  // Stable object identity while the three params are unchanged (used in query keys and effects).
  const filters = useMemo(() => {
    const p = new URLSearchParams()
    if (days !== null) p.set('days', days)
    if (source !== null) p.set('source', source)
    if (basis !== null) p.set('basis', basis)
    return parseFilters(p)
  }, [days, source, basis])

  const patch = useCallback(
    (name: string, value: string | undefined) =>
      setSp(
        (prev) => {
          const next = new URLSearchParams(prev)
          if (value === undefined) next.delete(name)
          else next.set(name, value)
          return next
        },
        { replace: true },
      ),
    [setSp],
  )

  const setDays = useCallback((days: number | undefined) => patch('days', days ? String(days) : undefined), [patch])
  const setSource = useCallback((source: SourceFilter) => patch('source', source === 'all' ? undefined : source), [patch])
  const setBasis = useCallback((basis: BasisFilter) => patch('basis', basis === 'all' ? undefined : basis), [patch])
  const setFallback = useCallback((on: boolean) => setBasis(on ? 'all' : 'post'), [setBasis])
  const reset = useCallback(
    () =>
      setSp(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const k of ['days', 'source', 'basis']) next.delete(k)
          return next
        },
        { replace: true },
      ),
    [setSp],
  )

  const isFiltered = filters.days !== undefined || filters.source !== 'all' || filters.basis !== 'all'
  return { filters, setDays, setSource, setBasis, setFallback, reset, isFiltered }
}
