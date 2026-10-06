// /: KPIs, posting volume (direct vs forwarded), top provinces and how ads are located.
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, type LabelProps } from 'recharts'
import { useLocations, useOverview } from '../api/hooks'
import type { Granularity, Locations, Overview } from '../api/types'
import { BarList } from '../components/ui/BarList'
import { Card } from '../components/ui/Card'
import { axisProps, gridProps, Legend, SplitBar, TooltipBox, yAxisProps } from '../components/ui/ChartParts'
import { DataTable } from '../components/ui/DataTable'
import { ChartSkeleton, Skeleton } from '../components/ui/Skeleton'
import { StatTile } from '../components/ui/StatTile'
import { QueryView } from '../components/ui/States'
import { FORWARDED_NOTE, LOCATION_SOURCES, PROVINCE_NAME_KO, SOURCE_LABELS } from '../lib/constants'
import { fmtBucket, fmtCompact, fmtInt, fmtKrwPeriod, fmtPct, relChange } from '../lib/format'
import { useLinkTo } from '../lib/links'
import { DIRECT_FORWARDED, INK_2, SOURCE_COLORS } from '../lib/palette'
import type { ProvinceId } from '../api/types'

const GRANULARITY_NOUN: Record<Granularity, string> = { day: 'day', week: 'week', month: 'month' }

export function OverviewPage() {
  const overview = useOverview()
  const locations = useLocations()
  return (
    <div className="space-y-4">
      <QueryView query={overview} skeleton={<OverviewSkeleton />}>
        {(data, stale) => (
          <>
            <Kpis data={data} />
            <VolumeCard data={data} stale={stale} />
            <div className="grid gap-4 lg:grid-cols-2">
              <TopProvinces data={data} stale={stale} />
              <QueryView query={locations} skeleton={<Skeleton className="h-64 w-full rounded-2xl" />}>
                {(loc, locStale) => <LocationSources data={loc} stale={locStale} repostShare={data.kpis.repost_share} />}
              </QueryView>
            </div>
          </>
        )}
      </QueryView>
    </div>
  )
}

function Kpis({ data }: { data: Overview }) {
  const k = data.kpis
  const week = relChange(k.last_7d, k.prev_7d)
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 2xl:grid-cols-[1.25fr_repeat(3,minmax(0,1fr))]">
      <div className="glass col-span-2 flex flex-col justify-center px-5 py-4 md:col-span-3 2xl:col-span-1 2xl:row-span-2">
        <div className="text-xs font-medium text-slate-500">Unique job ads</div>
        <div className="mt-1 text-5xl leading-none font-semibold tracking-tight text-slate-900">{fmtInt(k.unique_ads)}</div>
        <div className="mt-2 text-xs leading-5 text-slate-500">
          from {fmtInt(k.posts)} posts — {fmtPct(k.repost_share)} were reposts of the same ad
        </div>
      </div>
      <StatTile label="Last 24 hours" value={fmtInt(k.last_24h)} sub="unique ads" />
      <StatTile label="Last 7 days" value={fmtInt(k.last_7d)} delta={{ value: week, vs: 'vs previous 7 days' }} />
      <StatTile label="Forwarded by the bot" value={fmtPct(k.forwarded_share)} sub="of unique ads" />
      <StatTile label="State a salary" value={fmtPct(k.salary_share)} sub="of unique ads" />
      <StatTile
        label="Median daily pay"
        value={fmtKrwPeriod(k.median_pay.daily, 'daily')}
        sub={
          [k.median_pay.hourly !== null && fmtKrwPeriod(k.median_pay.hourly, 'hourly'), k.median_pay.monthly !== null && fmtKrwPeriod(k.median_pay.monthly, 'monthly')]
            .filter(Boolean)
            .join(' · ') || 'no hourly/monthly data'
        }
      />
      <StatTile label="Place named in the post" value={fmtPct(k.located_share)} sub="others: group location" />
    </div>
  )
}

function VolumeCard({ data, stale }: { data: Overview; stale: boolean }) {
  const { granularity, points } = data.volume
  const last = points.length - 1
  // When both series end at about the same height, nudge their end labels apart.
  const top = Math.max(1, ...points.map((p) => Math.max(p.direct, p.forwarded)))
  const close = last >= 0 && Math.abs(points[last].direct - points[last].forwarded) / top < 0.08
  const above = last >= 0 && points[last].direct >= points[last].forwarded ? 'direct' : 'forwarded'
  const endLabel = (series: 'direct' | 'forwarded') =>
    function EndLabel(props: LabelProps) {
      if (props.index !== last || props.x === undefined || props.y === undefined) return <g />
      return (
        <text x={Number(props.x) + 6} y={Number(props.y) + (close ? (series === above ? -7 : 7) : 0)} dy="0.35em" fontSize={11} fill={INK_2} fontWeight={600}>
          {fmtCompact(Number(props.value))}
          <tspan fontWeight={400} fill="#64748b">
            {' '}
            {series === 'direct' ? 'direct' : 'fwd'}
          </tspan>
        </text>
      )
    }

  const table = (
    <DataTable
      rows={[...points].reverse()}
      rowKey={(p) => p.t}
      columns={[
        { key: 't', header: GRANULARITY_NOUN[granularity] === 'day' ? 'Day' : GRANULARITY_NOUN[granularity] === 'week' ? 'Week of' : 'Month', cell: (p) => fmtBucket(p.t, granularity) },
        { key: 'direct', header: 'Direct', align: 'right', cell: (p) => fmtInt(p.direct) },
        { key: 'forwarded', header: 'Forwarded', align: 'right', cell: (p) => fmtInt(p.forwarded) },
        { key: 'total', header: 'Total', align: 'right', cell: (p) => fmtInt(p.direct + p.forwarded) },
      ]}
    />
  )

  return (
    <Card
      title={`Unique ads per ${GRANULARITY_NOUN[granularity]}`}
      subtitle={`By the date each ad was first posted${granularity === 'day' ? '' : `; the latest ${GRANULARITY_NOUN[granularity]} is still in progress`}`}
      table={table}
      stale={stale}
      footer={FORWARDED_NOTE}
    >
      <Legend
        className="mb-3"
        items={[
          { key: 'direct', label: 'Direct posts in groups', color: DIRECT_FORWARDED.direct, kind: 'line' },
          { key: 'forwarded', label: "Forwarded by the Ish e'lonlari bot", color: DIRECT_FORWARDED.forwarded, kind: 'line' },
        ]}
      />
      <div className="h-[280px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 72, bottom: 0, left: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="t" {...axisProps} minTickGap={28} tickFormatter={(t: string) => fmtBucket(t, granularity, true)} />
            <YAxis {...yAxisProps} tickFormatter={(v: number) => fmtCompact(v)} allowDecimals={false} />
            <Tooltip
              cursor={{ stroke: '#cbd5e1' }}
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <TooltipBox
                    title={fmtBucket(String(label), granularity)}
                    rows={[
                      { key: 'direct', label: 'Direct', value: fmtInt(Number(payload.find((p) => p.dataKey === 'direct')?.value ?? 0)), color: DIRECT_FORWARDED.direct, kind: 'line' },
                      { key: 'forwarded', label: 'Forwarded', value: fmtInt(Number(payload.find((p) => p.dataKey === 'forwarded')?.value ?? 0)), color: DIRECT_FORWARDED.forwarded, kind: 'line' },
                    ]}
                  />
                ) : null
              }
            />
            <Line type="linear" dataKey="direct" stroke={DIRECT_FORWARDED.direct} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }} label={endLabel('direct')} isAnimationActive={false} />
            <Line type="linear" dataKey="forwarded" stroke={DIRECT_FORWARDED.forwarded} strokeWidth={2} dot={false} activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }} label={endLabel('forwarded')} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}

function TopProvinces({ data, stale }: { data: Overview; stale: boolean }) {
  const linkTo = useLinkTo()
  const total = data.kpis.unique_ads
  return (
    <Card title="Top provinces" subtitle="Unique ads — click to open on the map" stale={stale}>
      {data.top_provinces.length ? (
        <BarList
          items={data.top_provinces.map((p) => ({
            key: p.province,
            label: (
              <>
                {p.province} <span className="text-[11px] text-slate-400">{PROVINCE_NAME_KO[p.province as ProvinceId]}</span>
              </>
            ),
            value: p.ads,
            display: (
              <>
                {fmtInt(p.ads)} <span className="ml-1 text-[11px] font-normal text-slate-500">{fmtPct(total ? p.ads / total : 0)}</span>
              </>
            ),
            to: linkTo('/map', { region: p.province }),
          }))}
        />
      ) : (
        <div className="py-8 text-center text-[13px] text-slate-500">No placed ads in this period</div>
      )}
    </Card>
  )
}

function LocationSources({ data, stale, repostShare }: { data: Locations; stale: boolean; repostShare: number }) {
  const parts = LOCATION_SOURCES.map((s) => ({ key: s, value: data.sources[s], color: SOURCE_COLORS[s], label: SOURCE_LABELS[s] }))
  const nationwide = data.unplaced.nationwide
  return (
    <Card title="How each ad's location is found" subtitle="Checked in this order; the first that matches wins" stale={stale}>
      <SplitBar parts={parts} height={14} />
      <ul className="mt-3 space-y-2 text-[13px]">
        {parts.map((p) => (
          <li key={p.key} className="flex items-baseline justify-between gap-3">
            <span className="flex items-center gap-2 text-slate-700">
              <span className="size-2.5 shrink-0 rounded-[3px]" style={{ backgroundColor: p.color }} aria-hidden />
              {p.label}
            </span>
            <span className="tabular-nums">
              <span className="font-medium text-slate-900">{fmtPct(data.total ? p.value / data.total : 0)}</span>
              <span className="ml-2 inline-block w-14 text-right text-xs text-slate-500">{fmtInt(p.value)}</span>
            </span>
          </li>
        ))}
      </ul>
      <p className="mt-4 text-xs leading-5 text-slate-500">
        {fmtPct(data.total ? nationwide / data.total : 0)} of ads come from nationwide groups and cannot be placed on the map. Counts are unique ads:{' '}
        {fmtPct(repostShare)} of posts repeat an ad already counted.
      </p>
    </Card>
  )
}

function OverviewSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} className="h-24 w-full rounded-2xl" />
        ))}
      </div>
      <div className="glass p-5">
        <Skeleton className="mb-4 h-5 w-48" />
        <ChartSkeleton height={280} />
      </div>
    </div>
  )
}
