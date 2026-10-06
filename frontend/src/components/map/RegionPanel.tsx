// Right sidebar on /map: national summary when nothing is selected, otherwise details of the selected province.
import clsx from 'clsx'
import { MousePointerClick, X } from 'lucide-react'
import type { ReactNode } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useLocations, useRegion } from '../../api/hooks'
import type { Locations, Region } from '../../api/types'
import { useNow } from '../../hooks/useNow'
import { useSelectedRegion } from '../../hooks/useSelectedRegion'
import { LOCATION_SOURCES, PERIOD_LABELS, SOURCE_LABELS } from '../../lib/constants'
import { fmtBucket, fmtInt, fmtKrw, fmtKrwPeriod, fmtPct, fmtRelative } from '../../lib/format'
import { PERIOD_COLORS, SCRIPT_COLORS, SERIES, SOURCE_COLORS } from '../../lib/palette'
import { useFilters } from '../../state/filters'
import { FeedItemCard } from '../live/FeedItemCard'
import { Badge } from '../ui/Badge'
import { BarList } from '../ui/BarList'
import { Legend, SplitBar, TooltipBox } from '../ui/ChartParts'
import { Skeleton, SkeletonText } from '../ui/Skeleton'
import { ErrorState } from '../ui/States'

const GRANULARITY_LABEL = { day: 'day', week: 'week', month: 'month' } as const

function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="border-t border-slate-900/[0.06] px-4 py-3.5">
      <div className="mb-2 flex items-baseline justify-between gap-2">
        <h3 className="text-xs font-semibold tracking-wide text-slate-500 uppercase">{title}</h3>
        {aside && <span className="text-[11px] text-slate-500">{aside}</span>}
      </div>
      {children}
    </section>
  )
}

export function RegionPanel() {
  const [region, setRegion] = useSelectedRegion()
  return (
    <aside aria-label="Region details" className="glass flex h-full flex-col overflow-hidden">
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
        {region ? <RegionDetails id={region} onClose={() => setRegion(null)} /> : <NationalSummary />}
      </div>
    </aside>
  )
}

function NationalSummary() {
  const locations = useLocations()
  const { filters } = useFilters()
  const data = locations.data
  if (!data) {
    return locations.isError ? (
      <div className="p-4">
        <ErrorState error={locations.error} onRetry={() => void locations.refetch()} />
      </div>
    ) : (
      <PanelSkeleton />
    )
  }
  const placed = data.provinces.reduce((s, p) => s + p.ads, 0)
  return (
    <div className={clsx('transition-opacity', locations.isPlaceholderData && 'opacity-55')}>
      <header className="px-4 pt-4 pb-3">
        <h2 className="text-[15px] font-semibold text-slate-900">All of Korea</h2>
        <div className="mt-2 text-[28px] leading-8 font-semibold tracking-tight text-slate-900">{fmtInt(data.total)}</div>
        <div className="text-xs text-slate-500">
          unique ads · {fmtPct(data.total ? placed / data.total : 0)} placed on the map
        </div>
        <div className="mt-3 flex items-center gap-2 rounded-xl bg-blue-600/[0.07] px-3 py-2 text-[13px] text-blue-800">
          <MousePointerClick className="size-4 shrink-0" aria-hidden />
          Click a region on the map for its details
        </div>
      </header>
      <SourcesSection data={data} />
      <Section title="Not on the map">
        <ul className="space-y-1.5 text-[13px]">
          <UnplacedRow label="From nationwide groups" value={data.unplaced.nationwide} total={data.total} />
          <UnplacedRow label="No location found" value={data.unplaced.unknown} total={data.total} />
          {filters.basis === 'post' && (
            <UnplacedRow label="Only the group's home location" value={data.unplaced.group_fallback} total={data.total} />
          )}
        </ul>
      </Section>
    </div>
  )
}

function UnplacedRow({ label, value, total }: { label: string; value: number; total: number }) {
  return (
    <li className="flex items-baseline justify-between gap-3">
      <span className="text-slate-600">{label}</span>
      <span className="font-medium text-slate-900 tabular-nums">
        {fmtInt(value)} <span className="font-normal text-slate-500">({fmtPct(total ? value / total : 0)})</span>
      </span>
    </li>
  )
}

function SourcesSection({ data }: { data: Locations }) {
  const parts = LOCATION_SOURCES.map((s) => ({ key: s, value: data.sources[s], color: SOURCE_COLORS[s], label: SOURCE_LABELS[s] }))
  return (
    <Section title="How the location was found">
      <SplitBar parts={parts} />
      <ul className="mt-2.5 space-y-1 text-[13px]">
        {parts.map((p) => (
          <li key={p.key} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-1.5 text-slate-600">
              <span className="size-2.5 rounded-[3px]" style={{ backgroundColor: p.color }} aria-hidden />
              {p.label}
            </span>
            <span className="text-slate-900 tabular-nums">{fmtPct(data.total ? p.value / data.total : 0)}</span>
          </li>
        ))}
      </ul>
    </Section>
  )
}

function RegionDetails({ id, onClose }: { id: string; onClose: () => void }) {
  const query = useRegion(id)
  const now = useNow(30_000)
  const data = query.data
  if (!data) {
    return query.isError ? (
      <div className="p-4">
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      </div>
    ) : (
      <PanelSkeleton />
    )
  }
  const stale = query.isPlaceholderData || data.province !== id
  return (
    <div className={clsx('transition-opacity', stale && 'opacity-55')}>
      <header className="px-4 pt-4 pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h2 className="text-lg leading-6 font-semibold text-slate-900">
              {data.province} <span className="font-normal text-slate-500">{data.name_ko}</span>
            </h2>
            <div className="mt-1 flex items-center gap-2">
              <Badge tone="blue">#{data.rank} of 17</Badge>
              <span className="text-xs text-slate-500">{fmtPct(data.share)} of placed ads</span>
            </div>
          </div>
          <button type="button" onClick={onClose} aria-label="Clear selection" className="rounded-lg p-1 text-slate-400 hover:bg-white/60 hover:text-slate-900">
            <X className="size-4" aria-hidden />
          </button>
        </div>
        <div className="mt-3 text-[28px] leading-8 font-semibold tracking-tight text-slate-900">{fmtInt(data.ads)}</div>
        <div className="text-xs text-slate-500">unique ads in this period</div>
        <Trend data={data} />
      </header>

      <Section title="How the location was found">
        <SplitBar
          parts={(['address', 'text', 'group'] as const).map((s) => ({ key: s, value: data.by_source[s], color: SOURCE_COLORS[s], label: SOURCE_LABELS[s] }))}
        />
        <Legend
          className="mt-2"
          items={(['address', 'text', 'group'] as const).map((s) => ({
            key: s,
            color: SOURCE_COLORS[s],
            label: `${SOURCE_LABELS[s]} ${fmtPct(data.ads ? data.by_source[s] / data.ads : 0)}`,
          }))}
        />
      </Section>

      <Section title="Pay (median)">
        <ul className="space-y-2">
          {data.pay.map((p) => (
            <li key={p.period} className="flex items-baseline justify-between gap-3 text-[13px]">
              <span className="flex items-center gap-1.5 text-slate-600">
                <span className="size-2.5 rounded-full" style={{ backgroundColor: PERIOD_COLORS[p.period] }} aria-hidden />
                {PERIOD_LABELS[p.period]}
              </span>
              <span className="text-right">
                <span className="font-semibold text-slate-900 tabular-nums">{fmtKrwPeriod(p.median, p.period)}</span>
                <span className="ml-1.5 text-[11px] text-slate-500">
                  {p.ads > 0 ? `${fmtKrw(p.q1)}–${fmtKrw(p.q3)} · ${fmtInt(p.ads)} ads` : 'no ads'}
                </span>
              </span>
            </li>
          ))}
        </ul>
      </Section>

      {data.cities.length > 0 && (
        <Section title="Cities">
          <BarList items={data.cities.slice(0, 6).map((c) => ({ key: c.city, label: c.city, value: c.ads }))} />
        </Section>
      )}

      <Section title="Occupations" aside="named in the ad">
        {data.occupations.some((o) => o.ads > 0) ? (
          <BarList items={data.occupations.filter((o) => o.ads > 0).slice(0, 5).map((o) => ({ key: o.name, label: o.name, value: o.ads }))} />
        ) : (
          <div className="text-[13px] text-slate-500">No occupation named</div>
        )}
      </Section>

      {data.visas.length > 0 && (
        <Section title="Visas">
          <div className="flex flex-wrap gap-1.5">
            {data.visas.slice(0, 8).map((v) => (
              <Badge key={v.name} tone="indigo">
                {v.name} <span className="tabular-nums opacity-70">{fmtInt(v.ads)}</span>
              </Badge>
            ))}
          </div>
        </Section>
      )}

      <Section title="Written in">
        <SplitBar parts={(['Latin', 'Cyrillic', 'Hangul'] as const).map((s) => ({ key: s, value: data.scripts[s], color: SCRIPT_COLORS[s], label: s }))} height={8} />
        <Legend
          className="mt-2"
          items={(['Latin', 'Cyrillic', 'Hangul'] as const).map((s) => ({ key: s, color: SCRIPT_COLORS[s], label: `${s} ${fmtPct(data.scripts[s])}` }))}
        />
      </Section>

      {data.groups.length > 0 && (
        <Section title="Telegram groups" aside="ads here">
          <ul className="space-y-2">
            {data.groups.slice(0, 6).map((g) => (
              <li key={g.source_file} className="flex items-start justify-between gap-3 text-[13px]">
                <div className="min-w-0">
                  <div className="truncate text-slate-800" title={g.title}>
                    {g.title}
                  </div>
                  <div className="text-[11px] text-slate-500">
                    {g.home_province ? `Home: ${g.home_province}` : 'No home location'} · last {fmtRelative(g.last_post, now)}
                  </div>
                </div>
                <span className="shrink-0 font-medium text-slate-900 tabular-nums">{fmtInt(g.ads)}</span>
              </li>
            ))}
          </ul>
        </Section>
      )}

      <Section title="Latest ads">
        <div className="space-y-2">
          {data.latest.length ? data.latest.map((item) => <FeedItemCard key={item.id} item={item} now={now} />) : <div className="text-[13px] text-slate-500">No ads in this period</div>}
        </div>
      </Section>
    </div>
  )
}

function Trend({ data }: { data: Region }) {
  const points = data.trend.points
  if (points.length < 2) return null
  return (
    <div className="mt-3">
      <div className="mb-1 text-[11px] text-slate-500">Unique ads per {GRANULARITY_LABEL[data.trend.granularity]}</div>
      <div className="h-[72px]">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={points} margin={{ top: 4, right: 2, bottom: 0, left: 2 }}>
            <XAxis dataKey="t" hide />
            <YAxis hide domain={[0, 'dataMax']} />
            <Tooltip
              cursor={{ stroke: '#cbd5e1' }}
              content={({ active, payload }) =>
                active && payload?.length ? (
                  <TooltipBox
                    title={fmtBucket(String(payload[0].payload.t), data.trend.granularity)}
                    rows={[{ key: 'ads', label: 'Unique ads', value: fmtInt(Number(payload[0].value)) }]}
                  />
                ) : null
              }
            />
            <Area type="monotone" dataKey="ads" stroke={SERIES[0]} strokeWidth={2} fill={SERIES[0]} fillOpacity={0.1} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function PanelSkeleton() {
  return (
    <div className="space-y-4 p-4">
      <Skeleton className="h-5 w-40" />
      <Skeleton className="h-8 w-28" />
      <Skeleton className="h-16 w-full" />
      <SkeletonText lines={4} />
      <SkeletonText lines={3} />
    </div>
  )
}
