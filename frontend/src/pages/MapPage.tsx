// /map: province choropleth with legend, a ranked province list (also the table view) and "not on the map" counts.
import clsx from 'clsx'
import { useEffect, useMemo } from 'react'
import { useLocations } from '../api/hooks'
import type { Locations, ProvinceId } from '../api/types'
import { KoreaMap } from '../components/map/KoreaMap'
import { mapScale, type MapScale } from '../components/map/mapScale'
import { Card } from '../components/ui/Card'
import { ChartSkeleton, Skeleton } from '../components/ui/Skeleton'
import { QueryView } from '../components/ui/States'
import { useSelectedRegion } from '../hooks/useSelectedRegion'
import { fmtCompact, fmtInt, fmtPct } from '../lib/format'
import { MAP_ZERO } from '../lib/palette'
import { useFilters } from '../state/filters'

export function MapPage() {
  const query = useLocations()
  const [region, setRegion] = useSelectedRegion()

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setRegion(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [setRegion])

  return (
    <QueryView
      query={query}
      skeleton={
        <div className="glass p-5">
          <Skeleton className="mb-4 h-5 w-48" />
          <ChartSkeleton height={560} />
        </div>
      }
    >
      {(data, stale) => <MapCard data={data} stale={stale} selected={region} onSelect={setRegion} />}
    </QueryView>
  )
}

function MapCard({ data, stale, selected, onSelect }: { data: Locations; stale: boolean; selected: ProvinceId | null; onSelect: (id: ProvinceId | null) => void }) {
  const { filters } = useFilters()
  const scale = useMemo(() => mapScale(data.provinces.map((p) => p.ads)), [data])
  const placed = data.provinces.reduce((s, p) => s + p.ads, 0)
  const groupShare = placed ? data.provinces.reduce((s, p) => s + p.by_source.group, 0) / placed : 0
  const subtitle =
    filters.basis === 'post'
      ? 'Only places named in the post itself (Korean address or place name). Ads that rely on the group’s home location are left off the map.'
      : `${fmtPct(groupShare)} of these ads are placed by the Telegram group’s home location, because the post names no place. Turn off "Group location fallback" to count only places named in posts.`

  return (
    <Card title="Unique ads by province" subtitle={subtitle} stale={stale}>
      <div className="@container">
        <div className="grid gap-6 @3xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0">
            <KoreaMap locations={data} scale={scale} selected={selected} onSelect={onSelect} />
            <MapLegend scale={scale} />
          </div>
          <div className="min-w-0">
            <ProvinceList data={data} placed={placed} scale={scale} selected={selected} onSelect={onSelect} />
            <Unplaced data={data} basisPost={filters.basis === 'post'} />
          </div>
        </div>
      </div>
    </Card>
  )
}

function MapLegend({ scale }: { scale: MapScale }) {
  return (
    <div className="mt-3 flex flex-wrap items-end gap-x-4 gap-y-2 text-[11px] text-slate-500">
      <span className="pb-0.5 text-xs font-medium text-slate-600">Unique ads</span>
      <div className="flex items-end gap-1.5">
        <div className="flex flex-col items-center gap-1">
          <span className="h-3 w-7 rounded-[3px] ring-1 ring-slate-900/[0.06] ring-inset" style={{ backgroundColor: MAP_ZERO }} />
          <span>0</span>
        </div>
        <div className="flex">
          {scale.classes.map((c, i) => (
            <div key={c.step} className="flex w-11 flex-col">
              <span className={clsx('h-3', i === 0 && 'rounded-l-[3px]', i === scale.classes.length - 1 && 'rounded-r-[3px]')} style={{ backgroundColor: c.color }} />
              <span className="mt-1 -ml-1 tabular-nums">{fmtCompact(c.from)}</span>
            </div>
          ))}
        </div>
      </div>
      <span className="pb-0.5">Darker = more ads (log scale)</span>
    </div>
  )
}

function ProvinceList({
  data,
  placed,
  scale,
  selected,
  onSelect,
}: {
  data: Locations
  placed: number
  scale: MapScale
  selected: ProvinceId | null
  onSelect: (id: ProvinceId | null) => void
}) {
  const ranked = [...data.provinces].sort((a, b) => b.ads - a.ads)
  const top = Math.max(1, ranked[0]?.ads ?? 1)
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between text-xs text-slate-500">
        <span className="font-medium text-slate-600">Ranking</span>
        <span>ads · share of placed</span>
      </div>
      <ol className="space-y-0.5">
        {ranked.map((p, i) => {
          const id = p.province as ProvinceId
          const active = selected === id
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => onSelect(active ? null : id)}
                aria-pressed={active}
                className={clsx(
                  'grid w-full grid-cols-[20px_minmax(0,1fr)_auto] items-center gap-x-2 rounded-lg px-1.5 py-1 text-left text-[13px] transition-colors',
                  active ? 'bg-blue-600/10' : 'hover:bg-blue-500/[0.06]',
                )}
              >
                <span className="text-right text-[11px] text-slate-400 tabular-nums">{i + 1}</span>
                <span className="min-w-0">
                  <span className="flex items-baseline gap-1.5">
                    <span className={clsx('truncate', active ? 'font-semibold text-blue-800' : 'text-slate-700')}>{p.province}</span>
                    <span className="text-[11px] text-slate-400">{p.name_ko}</span>
                  </span>
                  <span className="mt-0.5 block h-1.5 rounded-r-[3px] bg-slate-900/[0.04]">
                    <span className="block h-full rounded-r-[3px]" style={{ width: `${(p.ads / top) * 100}%`, backgroundColor: scale.fill(p.ads) }} />
                  </span>
                </span>
                <span className="text-right tabular-nums">
                  <span className="font-medium text-slate-900">{fmtInt(p.ads)}</span>
                  <span className="ml-1.5 inline-block w-9 text-[11px] text-slate-500">{placed ? fmtPct(p.ads / placed) : '—'}</span>
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </div>
  )
}

function Unplaced({ data, basisPost }: { data: Locations; basisPost: boolean }) {
  const chips = [
    { key: 'nationwide', label: 'Nationwide groups', value: data.unplaced.nationwide, title: 'Ads from groups that cover all of Korea and name no place' },
    { key: 'unknown', label: 'No location', value: data.unplaced.unknown, title: 'No place in the text and no home location for the group' },
    ...(basisPost
      ? [{ key: 'fallback', label: 'Group location only', value: data.unplaced.group_fallback, title: 'Placed only by the group’s home location (fallback is off)' }]
      : []),
  ]
  return (
    <div className="mt-4 border-t border-slate-900/[0.06] pt-3">
      <div className="mb-2 text-xs font-medium text-slate-600">Not on the map</div>
      <div className="flex flex-wrap gap-1.5">
        {chips.map((c) => (
          <span key={c.key} title={c.title} className="inline-flex items-baseline gap-1.5 rounded-full bg-slate-500/10 px-2.5 py-1 text-xs text-slate-700">
            {c.label}
            <span className="font-semibold text-slate-900 tabular-nums">{fmtInt(c.value)}</span>
            <span className="text-slate-500">{fmtPct(data.total ? c.value / data.total : 0)}</span>
          </span>
        ))}
      </div>
    </div>
  )
}
