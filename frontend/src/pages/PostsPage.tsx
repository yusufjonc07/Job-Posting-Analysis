// /posts: script by year, contact/link flags, post length (log-scale histogram) and how often ads are reposted.
import { scaleLinear, scaleLog } from 'd3-scale'
import { useState } from 'react'
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { usePosts } from '../api/hooks'
import type { Posts } from '../api/types'
import { BarList } from '../components/ui/BarList'
import { Card } from '../components/ui/Card'
import { axisProps, gridProps, Legend, TooltipBox, yAxisProps } from '../components/ui/ChartParts'
import { DataTable } from '../components/ui/DataTable'
import { Skeleton } from '../components/ui/Skeleton'
import { EmptyState, QueryView } from '../components/ui/States'
import { useElementWidth } from '../hooks/useElementWidth'
import { fmtCompact, fmtInt, fmtPct } from '../lib/format'
import { AXIS, GRID, INK_2, MUTED, SCRIPT_COLORS, SERIES } from '../lib/palette'

const SCRIPTS = ['Latin', 'Cyrillic', 'Hangul'] as const

export function PostsPage() {
  const query = usePosts()
  return (
    <QueryView
      query={query}
      skeleton={
        <div className="grid gap-4 lg:grid-cols-2">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-72 rounded-2xl" />
          ))}
        </div>
      }
    >
      {(data, stale) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <ScriptsCard rows={data.scripts} stale={stale} />
          <FlagsCard flags={data.flags} stale={stale} />
          <LengthCard length={data.length} stale={stale} />
          <RepostsCard rows={data.reposts} stale={stale} />
        </div>
      )}
    </QueryView>
  )
}

function ScriptsCard({ rows, stale }: { rows: Posts['scripts']; stale: boolean }) {
  const table = (
    <DataTable
      rows={rows}
      rowKey={(r) => String(r.year)}
      columns={[
        { key: 'y', header: 'Year', cell: (r) => r.year },
        ...SCRIPTS.map((s) => ({ key: s, header: s, align: 'right' as const, cell: (r: Posts['scripts'][number]) => fmtPct(r[s]) })),
      ]}
    />
  )
  return (
    <Card title="Main script by year" subtitle="Share of unique ads by the alphabet most of the text uses (Korea time)" table={table} stale={stale}>
      <Legend className="mb-3" items={SCRIPTS.map((s) => ({ key: s, label: s, color: SCRIPT_COLORS[s] }))} />
      {rows.length === 0 ? (
        <EmptyState title="No ads in this period" />
      ) : (
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="year" {...axisProps} />
              <YAxis {...yAxisProps} width={40} domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tickFormatter={(v: number) => fmtPct(v, 0)} />
              <Tooltip
                cursor={{ fill: 'rgba(15,23,42,0.04)' }}
                content={({ active, payload }) => {
                  const row = payload?.[0]?.payload as Posts['scripts'][number] | undefined
                  return active && row ? (
                    <TooltipBox title={String(row.year)} rows={[...SCRIPTS].reverse().map((s) => ({ key: s, label: s, value: fmtPct(row[s]), color: SCRIPT_COLORS[s] }))} />
                  ) : null
                }}
              />
              {SCRIPTS.map((s, i) => (
                <Bar
                  key={s}
                  dataKey={s}
                  stackId="script"
                  fill={SCRIPT_COLORS[s]}
                  stroke="#ffffff"
                  strokeWidth={1}
                  maxBarSize={24}
                  radius={i === SCRIPTS.length - 1 ? [4, 4, 0, 0] : 0}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

function FlagsCard({ flags, stale }: { flags: Posts['flags']; stale: boolean }) {
  return (
    <Card title="What ads include" subtitle="Share of unique ads" stale={stale}>
      <BarList max={1} items={flags.map((f) => ({ key: f.key, label: f.label, value: f.share, display: fmtPct(f.share) }))} />
      <p className="mt-4 text-xs leading-5 text-slate-500">
        Most ads ask people to write privately instead of giving a phone number. "Marked filled" ads were edited by the bot to say the job is taken.
      </p>
    </Card>
  )
}

function LengthCard({ length, stale }: { length: Posts['length']; stale: boolean }) {
  const [ref, width] = useElementWidth()
  const [hover, setHover] = useState<number | null>(null)
  const height = 200
  const m = { top: 8, right: 8, bottom: 22, left: 40 }
  const bins = length.bins
  const x = scaleLog()
    .domain([1, 10_000])
    .range([m.left, Math.max(m.left + 1, width - m.right)])
  const y = scaleLinear()
    .domain([0, Math.max(1, ...bins.map((b) => b.ads))])
    .nice()
    .range([height - m.bottom, m.top])
  const yTicks = y.ticks(4)
  const table = (
    <DataTable
      rows={bins.filter((b) => b.ads > 0)}
      rowKey={(b) => String(b.x0)}
      columns={[
        { key: 'r', header: 'Characters', cell: (b) => `${fmtInt(Math.ceil(b.x0))} – ${fmtInt(Math.floor(b.x1))}` },
        { key: 'n', header: 'Ads', align: 'right', cell: (b) => fmtInt(b.ads) },
      ]}
    />
  )
  const active = hover !== null ? bins[hover] : null
  return (
    <Card title="Ad length" subtitle={`Characters of job text, log scale · median ${fmtInt(length.median)} characters`} table={table} stale={stale}>
      <div ref={ref} className="relative">
        {width > 0 && (
          <svg width={width} height={height} role="img" aria-label="Histogram of ad length in characters">
            {yTicks.map((t) => (
              <g key={t}>
                <line x1={m.left} x2={width - m.right} y1={y(t)} y2={y(t)} stroke={GRID} />
                <text x={m.left - 6} y={y(t)} dy="0.35em" textAnchor="end" fontSize={11} fill={MUTED}>
                  {fmtCompact(t)}
                </text>
              </g>
            ))}
            {bins.map((b, i) => {
              const x0 = x(Math.max(1, b.x0)) + 1
              const x1 = x(b.x1) - 1
              const top = y(b.ads)
              const h = height - m.bottom - top
              return (
                <g key={b.x0} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <rect x={x(Math.max(1, b.x0))} width={Math.max(1, x(b.x1) - x(Math.max(1, b.x0)))} y={m.top} height={height - m.bottom - m.top} fill="transparent" />
                  {b.ads > 0 && (
                    <path
                      d={`M${x0},${height - m.bottom} V${top + Math.min(3, h)} Q${x0},${top} ${x0 + Math.min(3, (x1 - x0) / 2)},${top} H${x1 - Math.min(3, (x1 - x0) / 2)} Q${x1},${top} ${x1},${top + Math.min(3, h)} V${height - m.bottom} Z`}
                      fill={SERIES[0]}
                      opacity={hover === null || hover === i ? 1 : 0.55}
                    />
                  )}
                </g>
              )
            })}
            <line x1={m.left} x2={width - m.right} y1={height - m.bottom} y2={height - m.bottom} stroke={AXIS} />
            <line x1={x(length.median)} x2={x(length.median)} y1={m.top} y2={height - m.bottom} stroke={INK_2} strokeWidth={1.5} />
            {[1, 10, 100, 1000, 10_000].map((t) => (
              <text key={t} x={x(t)} y={height - 6} textAnchor={t === 1 ? 'start' : t === 10_000 ? 'end' : 'middle'} fontSize={11} fill={MUTED}>
                {fmtInt(t)}
              </text>
            ))}
          </svg>
        )}
        {active && hover !== null && (
          <div className="pointer-events-none absolute z-10" style={{ left: Math.min(x(active.x1) + 8, width - 170), top: 8 }}>
            <TooltipBox title={`${fmtInt(Math.ceil(active.x0))} – ${fmtInt(Math.floor(active.x1))} characters`} rows={[{ key: 'n', label: 'Ads', value: fmtInt(active.ads), color: SERIES[0] }]} />
          </div>
        )}
      </div>
      <div className="mt-1 text-[11px] text-slate-500">Vertical line = median</div>
    </Card>
  )
}

function RepostsCard({ rows, stale }: { rows: Posts['reposts']; stale: boolean }) {
  const table = (
    <DataTable
      rows={rows}
      rowKey={(r) => r.bucket}
      columns={[
        { key: 'b', header: 'Ad posted', cell: (r) => r.bucket },
        { key: 'u', header: 'Unique ads', align: 'right', cell: (r) => fmtInt(r.unique_ads) },
        { key: 'p', header: 'Posts', align: 'right', cell: (r) => fmtInt(r.posts) },
        { key: 's', header: 'Share of posts', align: 'right', cell: (r) => fmtPct(r.share_of_posts) },
      ]}
    />
  )
  return (
    <Card title="How often the same ad is posted" subtitle="Share of all posts, by how many times their ad text was posted" table={table} stale={stale}>
      <div className="h-[220px]">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 20, right: 8, bottom: 0, left: 0 }}>
            <CartesianGrid {...gridProps} />
            <XAxis dataKey="bucket" {...axisProps} interval={0} tickFormatter={(b: string) => (b === 'once' ? '1×' : b.replace(' times', '×'))} />
            <YAxis {...yAxisProps} width={40} tickFormatter={(v: number) => fmtPct(v, 0)} />
            <Tooltip
              cursor={{ fill: 'rgba(15,23,42,0.04)' }}
              content={({ active, payload }) => {
                const row = payload?.[0]?.payload as Posts['reposts'][number] | undefined
                return active && row ? (
                  <TooltipBox
                    title={`Posted ${row.bucket}`}
                    rows={[
                      { key: 's', label: 'Share of posts', value: fmtPct(row.share_of_posts), color: SERIES[0] },
                      { key: 'p', label: 'Posts', value: fmtInt(row.posts) },
                      { key: 'u', label: 'Unique ads', value: fmtInt(row.unique_ads) },
                    ]}
                  />
                ) : null
              }}
            />
            <Bar dataKey="share_of_posts" fill={SERIES[0]} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
              <LabelList dataKey="share_of_posts" position="top" formatter={(v: unknown) => fmtPct(Number(v))} fontSize={11} fill={INK_2} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Card>
  )
}
