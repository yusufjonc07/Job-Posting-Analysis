// /jobs: occupations and visa types named in ads, and an occupation × province heatmap.
import clsx from 'clsx'
import { useState } from 'react'
import { Link } from 'react-router'
import { useJobs } from '../api/hooks'
import type { Jobs, ProvinceId } from '../api/types'
import { BarList } from '../components/ui/BarList'
import { Card } from '../components/ui/Card'
import { TooltipBox } from '../components/ui/ChartParts'
import { DataTable } from '../components/ui/DataTable'
import { Skeleton } from '../components/ui/Skeleton'
import { EmptyState, QueryView } from '../components/ui/States'
import { PROVINCE_NAME_KO } from '../lib/constants'
import { fmtCompact, fmtInt, fmtPct } from '../lib/format'
import { useLinkTo } from '../lib/links'
import { MAP_RAMP, MAP_ZERO, mapLabelInk, SERIES } from '../lib/palette'

export function JobsPage() {
  const query = useJobs()
  return (
    <QueryView
      query={query}
      skeleton={
        <div className="grid gap-4 lg:grid-cols-2">
          <Skeleton className="h-80 rounded-2xl" />
          <Skeleton className="h-80 rounded-2xl" />
        </div>
      }
    >
      {(data, stale) => (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-2">
            <NamedList
              title="Occupations"
              subtitle={`${fmtPct(data.named_share)} of ads name at least one; an ad can name several`}
              rows={data.occupations}
              stale={stale}
              color={SERIES[0]}
            />
            <NamedList
              title="Visa types"
              subtitle={`${fmtPct(data.visa_share)} of ads mention a visa type`}
              rows={data.visas}
              stale={stale}
              color={SERIES[0]}
            />
          </div>
          <Heatmap matrix={data.matrix} stale={stale} />
          <p className="glass px-5 py-3.5 text-xs leading-5 text-slate-600">
            Occupations are found with keyword patterns in Uzbek (Latin and Cyrillic), Russian loanwords and Korean — for example "zavod",
            "공장" or "fabrika" for factory work — and visa types with patterns like "E-9" or "F4". It is a heuristic: ads that describe the work
            in other words are not counted, so treat the shares as lower bounds.
          </p>
        </div>
      )}
    </QueryView>
  )
}

/** 2 significant digits: 109 → 110, 4,321 → 4,300. */
function roundNice(v: number): number {
  if (v < 10) return Math.round(v)
  const mag = 10 ** (Math.floor(Math.log10(v)) - 1)
  return Math.round(v / mag) * mag
}

function NamedList({ title, subtitle, rows, stale, color }: { title: string; subtitle: string; rows: Jobs['occupations']; stale: boolean; color: string }) {
  const table = (
    <DataTable
      rows={rows}
      rowKey={(r) => r.name}
      columns={[
        { key: 'name', header: 'Name', cell: (r) => r.name },
        { key: 'ads', header: 'Ads', align: 'right', cell: (r) => fmtInt(r.ads) },
        { key: 'share', header: 'Share of ads', align: 'right', cell: (r) => fmtPct(r.share) },
      ]}
    />
  )
  return (
    <Card title={title} subtitle={subtitle} table={table} stale={stale}>
      {rows.length === 0 ? (
        <EmptyState title="None in this period" />
      ) : (
        <BarList
          color={color}
          items={rows.map((r) => ({
            key: r.name,
            label: r.name,
            value: r.ads,
            display: (
              <>
                {fmtInt(r.ads)} <span className="ml-1 inline-block w-10 text-[11px] font-normal text-slate-500">{fmtPct(r.share)}</span>
              </>
            ),
          }))}
        />
      )}
    </Card>
  )
}

function Heatmap({ matrix, stale }: { matrix: Jobs['matrix']; stale: boolean }) {
  const linkTo = useLinkTo()
  const [hover, setHover] = useState<{ p: number; o: number } | null>(null)
  const max = Math.max(1, ...matrix.cells.flat())
  // Square-root steps keep small counts visible next to the big provinces.
  const step = (v: number) => (v <= 0 ? -1 : Math.min(MAP_RAMP.length - 1, Math.ceil(Math.sqrt(v / max) * MAP_RAMP.length) - 1))
  const legend = MAP_RAMP.map((color, i) => ({ color, from: Math.max(1, roundNice(max * (i / MAP_RAMP.length) ** 2)) }))

  const table = (
    <DataTable
      rows={matrix.provinces.map((p, i) => ({ p, row: matrix.cells[i] }))}
      rowKey={(r) => r.p}
      columns={[
        { key: 'p', header: 'Province', cell: (r) => r.p },
        ...matrix.occupations.map((o, j) => ({ key: o, header: o, align: 'right' as const, cell: (r: { row: number[] }) => fmtInt(r.row[j]) })),
      ]}
    />
  )

  return (
    <Card
      title="Occupations by province"
      subtitle="Unique ads naming each occupation, in the 10 provinces with the most ads. Darker = more ads."
      table={table}
      stale={stale}
    >
      {matrix.provinces.length === 0 ? (
        <EmptyState title="No placed ads in this period" />
      ) : (
        <div className="@container">
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[640px] table-fixed border-separate border-spacing-0.5 text-[12px]">
              <thead>
                <tr>
                  <th className="w-44" />
                  {matrix.occupations.map((o) => (
                    <th key={o} scope="col" className="px-1 pb-1 text-center align-bottom text-[11px] leading-tight font-medium text-slate-500">
                      {o}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.provinces.map((p, i) => (
                  <tr key={p}>
                    <th scope="row" className="pr-2 text-left font-normal whitespace-nowrap">
                      <Link to={linkTo('/map', { region: p })} className="text-slate-700 hover:text-blue-700">
                        {p} <span className="text-[11px] text-slate-400">{PROVINCE_NAME_KO[p as ProvinceId]}</span>
                      </Link>
                    </th>
                    {matrix.cells[i].map((v, j) => {
                      const s = step(v)
                      const active = hover?.p === i && hover.o === j
                      return (
                        <td
                          key={j}
                          onMouseEnter={() => setHover({ p: i, o: j })}
                          onMouseLeave={() => setHover(null)}
                          className={clsx('relative h-9 rounded-[4px] text-center font-medium tabular-nums', active && 'ring-2 ring-slate-900 ring-inset')}
                          style={{ backgroundColor: s < 0 ? MAP_ZERO : MAP_RAMP[s], color: s < 0 ? '#94a3b8' : mapLabelInk(s) }}
                        >
                          <span className="hidden @lg:inline">{v > 0 ? fmtCompact(v) : '·'}</span>
                          {active && (
                            <div className="absolute bottom-full left-1/2 z-20 mb-1 -translate-x-1/2 text-left font-normal">
                              <TooltipBox
                                title={`${p} · ${matrix.occupations[j]}`}
                                rows={[
                                  { key: 'ads', label: 'Ads', value: fmtInt(v) },
                                  { key: 'share', label: `Share of ${matrix.occupations[j].toLowerCase()} ads here`, value: fmtPct(v / Math.max(1, matrix.cells.reduce((s2, r) => s2 + r[j], 0))) },
                                ]}
                              />
                            </div>
                          )}
                        </td>
                      )
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex items-end gap-3 text-[11px] text-slate-500">
            <span className="pb-0.5 text-xs font-medium text-slate-600">Ads</span>
            <div className="flex">
              {legend.map((l, i) => (
                <div key={l.color} className="flex w-10 flex-col">
                  <span className={clsx('h-3', i === 0 && 'rounded-l-[3px]', i === legend.length - 1 && 'rounded-r-[3px]')} style={{ backgroundColor: l.color }} />
                  <span className="mt-1 -ml-1 tabular-nums">{fmtCompact(l.from)}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </Card>
  )
}
