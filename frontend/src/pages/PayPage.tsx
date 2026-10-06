// /pay: salary distributions per pay period, quarterly medians (small multiples) and daily pay by province.
import { Bar, BarChart, CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router'
import { usePay } from '../api/hooks'
import type { Pay } from '../api/types'
import { Card } from '../components/ui/Card'
import { axisProps, gridProps, TooltipBox, yAxisProps } from '../components/ui/ChartParts'
import { DataTable } from '../components/ui/DataTable'
import { ChartSkeleton, Skeleton } from '../components/ui/Skeleton'
import { EmptyState, QueryView } from '../components/ui/States'
import { PERIOD_LABELS, PROVINCE_NAME_KO } from '../lib/constants'
import { fmtInt, fmtKrw, fmtKrwFull, fmtKrwPeriod, fmtQuarter, PERIOD_SUFFIX } from '../lib/format'
import { useLinkTo } from '../lib/links'
import { INK, INK_2, PERIOD_COLORS } from '../lib/palette'
import type { ProvinceId } from '../api/types'

type PeriodStats = Pay['periods'][number]
type TrendSeries = Pay['trend'][number]
type Bin = PeriodStats['bins'][number]

/** Histograms show at most this many bars; neighbouring bins are merged above it. */
const MAX_BARS = 36

function mergeBins(bins: Bin[], max: number): Bin[] {
  const k = Math.max(1, Math.ceil(bins.length / max))
  const merged: Bin[] = []
  for (let i = 0; i < bins.length; i += k) {
    const group = bins.slice(i, i + k)
    merged.push({ x0: group[0].x0, x1: group[group.length - 1].x1, ads: group.reduce((s, b) => s + b.ads, 0) })
  }
  return merged
}

export function PayPage() {
  const query = usePay()
  return (
    <QueryView query={query} skeleton={<PaySkeleton />}>
      {(data, stale) => (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-3">
            {data.periods.map((p) => (
              <PeriodCard key={p.period} stats={p} stale={stale} />
            ))}
          </div>
          <TrendCard trend={data.trend} stale={stale} />
          <ProvinceCard rows={data.by_province} stale={stale} />
          <p className="glass px-5 py-3.5 text-xs leading-5 text-slate-600">
            Only about 7% of ads state a salary, so these numbers describe that minority of ads. Amounts are read from the text (e.g. "130 ming",
            "2.8 mln"), classified by period, and anything outside a plausible range for its period is dropped. Medians land on round numbers
            because employers quote round amounts.
          </p>
        </div>
      )}
    </QueryView>
  )
}

function PeriodCard({ stats, stale }: { stats: PeriodStats; stale: boolean }) {
  const color = PERIOD_COLORS[stats.period]
  const bins = mergeBins(stats.bins, MAX_BARS)
  const data = bins.map((b, i) => ({ i, ...b }))
  const medianIndex = stats.median === null ? -1 : bins.findIndex((b) => stats.median! >= b.x0 && stats.median! < b.x1)
  const tickEvery = Math.ceil(bins.length / 5)
  const table = (
    <DataTable
      rows={bins}
      rowKey={(b) => String(b.x0)}
      columns={[
        { key: 'range', header: 'Amount (KRW)', cell: (b) => `${fmtKrw(b.x0)} – ${fmtKrw(b.x1)}` },
        { key: 'ads', header: 'Ads', align: 'right', cell: (b) => fmtInt(b.ads) },
      ]}
    />
  )
  return (
    <Card
      title={
        <span className="flex items-center gap-2">
          <span className="size-2.5 rounded-full" style={{ backgroundColor: color }} aria-hidden />
          {PERIOD_LABELS[stats.period]} pay
        </span>
      }
      subtitle={`${fmtInt(stats.ads)} ads · line = median`}
      table={table}
      stale={stale}
    >
      <div className="flex items-baseline gap-2">
        <span className="text-[28px] leading-8 font-semibold tracking-tight text-slate-900">{fmtKrwPeriod(stats.median, stats.period)}</span>
        <span className="text-xs text-slate-500">median</span>
      </div>
      <div className="mt-0.5 text-xs text-slate-500">
        Middle half: {fmtKrw(stats.q1)} – {fmtKrw(stats.q3)}
        {PERIOD_SUFFIX[stats.period]}
      </div>
      {stats.ads === 0 ? (
        <EmptyState title="No ads with this pay period" />
      ) : (
        <div className="mt-3 h-[180px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} barCategoryGap={1}>
              <CartesianGrid {...gridProps} />
              <XAxis
                dataKey="i"
                {...axisProps}
                ticks={data.filter((d) => d.i % tickEvery === 0).map((d) => d.i)}
                tickFormatter={(i: number) => fmtKrw(data[i]?.x0)}
              />
              <YAxis {...yAxisProps} width={36} allowDecimals={false} tickFormatter={(v: number) => fmtInt(v)} />
              <Tooltip
                cursor={{ fill: 'rgba(15,23,42,0.04)' }}
                content={({ active, payload }) => {
                  const row = payload?.[0]?.payload as (typeof data)[number] | undefined
                  return active && row ? (
                    <TooltipBox title={`${fmtKrw(row.x0)} – ${fmtKrw(row.x1)}${PERIOD_SUFFIX[stats.period]}`} rows={[{ key: 'ads', label: 'Ads', value: fmtInt(row.ads), color }]} />
                  ) : null
                }}
              />
              <Bar dataKey="ads" fill={color} radius={[3, 3, 0, 0]} maxBarSize={24} isAnimationActive={false} />
              {medianIndex >= 0 && <ReferenceLine x={medianIndex} stroke={INK} strokeWidth={1.5} />}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function TrendCard({ trend, stale }: { trend: TrendSeries[]; stale: boolean }) {
  const quarters = trend[0]?.points ?? []
  const table = (
    <DataTable
      rows={[...quarters.keys()].reverse()}
      rowKey={(i) => String(i)}
      columns={[
        { key: 'q', header: 'Quarter', cell: (i) => fmtQuarter(quarters[i].quarter) },
        ...trend.map((s) => ({
          key: s.period,
          header: `${PERIOD_LABELS[s.period]} median (ads)`,
          align: 'right' as const,
          cell: (i: number) => (
            <>
              {fmtKrw(s.points[i]?.median)} <span className="text-slate-400">({fmtInt(s.points[i]?.ads ?? 0)})</span>
            </>
          ),
        })),
      ]}
    />
  )
  return (
    <Card
      title="Median pay by quarter"
      subtitle="Each period on its own scale; quarters with fewer than 30 ads are left as gaps. The current quarter is not shown until it ends."
      table={table}
      stale={stale}
    >
      {quarters.length === 0 ? (
        <EmptyState title="Not enough salary data in this period" />
      ) : (
        <div className="grid gap-5 md:grid-cols-3">
          {trend.map((s) => (
            <TrendChart key={s.period} series={s} />
          ))}
        </div>
      )}
    </Card>
  )
}

function TrendChart({ series }: { series: TrendSeries }) {
  const color = PERIOD_COLORS[series.period]
  const points = series.points
  const lastIndex = points.reduce((found, p, i) => (p.median !== null ? i : found), -1)
  const last = lastIndex >= 0 ? points[lastIndex] : null
  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline justify-between gap-2 text-[13px]">
        <span className="flex items-center gap-1.5 font-medium text-slate-700">
          <span className="h-0.5 w-3 rounded-full" style={{ backgroundColor: color }} aria-hidden />
          {PERIOD_LABELS[series.period]}
        </span>
        {last && (
          <span className="text-xs text-slate-500">
            {fmtQuarter(last.quarter)}: <span className="font-semibold text-slate-900">{fmtKrwPeriod(last.median, series.period)}</span>
          </span>
        )}
      </div>
      <div className="h-[160px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={points} margin={{ top: 8, right: 10, bottom: 0, left: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="quarter" {...axisProps} minTickGap={24} tickFormatter={(q: string) => q.replace('Q', ' Q')} />
            <YAxis {...yAxisProps} width={40} domain={['auto', 'auto']} tickCount={4} tickFormatter={(v: number) => fmtKrw(v)} />
            <Tooltip
              cursor={{ stroke: '#cbd5e1' }}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as (typeof points)[number] | undefined
                return active && row ? (
                  <TooltipBox
                    title={fmtQuarter(row.quarter)}
                    rows={[
                      { key: 'm', label: 'Median', value: row.median === null ? 'too few ads' : fmtKrwFull(row.median), color, kind: 'line' },
                      { key: 'n', label: 'Ads', value: fmtInt(row.ads) },
                    ]}
                  />
                ) : null
              }}
            />
            <Line
              type="linear"
              dataKey="median"
              stroke={color}
              strokeWidth={2}
              connectNulls={false}
              dot={(props: { cx?: number; cy?: number; index?: number; value?: unknown }) =>
                props.cx !== undefined && props.cy !== undefined && props.value !== null && props.value !== undefined ? (
                  <circle
                    key={`d${props.index}`}
                    cx={props.cx}
                    cy={props.cy}
                    r={props.index === lastIndex ? 4 : 2.5}
                    fill={color}
                    stroke="#fff"
                    strokeWidth={props.index === lastIndex ? 2 : 1}
                  />
                ) : (
                  <g key={`d${props.index}`} />
                )
              }
              activeDot={{ r: 4, stroke: '#fff', strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function ProvinceCard({ rows, stale }: { rows: Pay['by_province']; stale: boolean }) {
  const linkTo = useLinkTo()
  const lo = Math.min(...rows.map((r) => r.q1))
  const hi = Math.max(...rows.map((r) => r.q3))
  const span = Math.max(1, hi - lo)
  const pos = (v: number) => `${((v - lo) / span) * 100}%`
  const ticks = niceTicks(lo, hi, 5)
  const table = (
    <DataTable
      rows={rows}
      rowKey={(r) => r.province}
      columns={[
        { key: 'p', header: 'Province', cell: (r) => r.province },
        { key: 'm', header: 'Median', align: 'right', cell: (r) => fmtKrwFull(r.median) },
        { key: 'r', header: 'Middle half', align: 'right', cell: (r) => `${fmtKrw(r.q1)} – ${fmtKrw(r.q3)}` },
        { key: 'n', header: 'Ads', align: 'right', cell: (r) => fmtInt(r.ads) },
      ]}
    />
  )
  return (
    <Card
      title="Daily pay by province"
      subtitle="Dot = median, line = middle half of ads (25th–75th percentile). Provinces with at least 30 daily-pay ads."
      table={table}
      stale={stale}
    >
      {rows.length === 0 ? (
        <EmptyState title="Too few daily-pay ads per province in this period" />
      ) : (
        <div>
          <ul className="space-y-1">
            {rows.map((r) => (
              <li key={r.province} className="grid grid-cols-[184px_minmax(0,1fr)_88px] items-center gap-3 text-[13px]">
                <Link to={linkTo('/map', { region: r.province })} className="truncate text-slate-700 hover:text-blue-700">
                  {r.province} <span className="text-[11px] text-slate-400">{PROVINCE_NAME_KO[r.province as ProvinceId]}</span>
                </Link>
                <div className="relative h-6" title={`${r.province}: median ${fmtKrwFull(r.median)}, middle half ${fmtKrw(r.q1)}–${fmtKrw(r.q3)}`}>
                  {ticks.map((t) => (
                    <span key={t} className="absolute inset-y-0 w-px bg-slate-200" style={{ left: pos(t) }} />
                  ))}
                  <span className="absolute top-1/2 h-0.5 -translate-y-1/2 rounded-full" style={{ left: pos(r.q1), width: `${((r.q3 - r.q1) / span) * 100}%`, backgroundColor: PERIOD_COLORS.daily, opacity: 0.45 }} />
                  <span
                    className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-white"
                    style={{ left: pos(r.median), backgroundColor: PERIOD_COLORS.daily }}
                  />
                </div>
                <span className="text-right tabular-nums">
                  <span className="font-medium text-slate-900">{fmtKrw(r.median)}</span>
                  <span className="ml-1.5 text-[11px] text-slate-500">{fmtInt(r.ads)}</span>
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-1 grid grid-cols-[184px_minmax(0,1fr)_88px] gap-3 text-[11px] text-slate-500">
            <span />
            <div className="relative h-4">
              {ticks.map((t) => (
                <span key={t} className="absolute -translate-x-1/2 tabular-nums" style={{ left: pos(t) }}>
                  {fmtKrw(t)}
                </span>
              ))}
            </div>
            <span className="text-right" style={{ color: INK_2 }}>
              median · ads
            </span>
          </div>
        </div>
      )}
    </Card>
  )
}

/** Round tick values inside [lo, hi]. */
function niceTicks(lo: number, hi: number, count: number): number[] {
  const raw = (hi - lo) / count
  const mag = 10 ** Math.floor(Math.log10(Math.max(raw, 1)))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? mag * 10
  const ticks: number[] = []
  for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t)
  return ticks
}

function PaySkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="glass p-5">
            <Skeleton className="mb-3 h-5 w-32" />
            <Skeleton className="mb-4 h-8 w-24" />
            <ChartSkeleton height={180} />
          </div>
        ))}
      </div>
      <Skeleton className="h-64 w-full rounded-2xl" />
    </div>
  )
}
