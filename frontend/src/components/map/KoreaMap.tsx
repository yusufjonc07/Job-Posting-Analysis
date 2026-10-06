// SVG choropleth of the 17 provinces: counts on the map, hover tooltip, click / keyboard selection, live pulses.
import type { Feature, FeatureCollection, MultiPolygon } from 'geojson'
import { geoArea, geoCentroid, geoMercator, geoPath } from 'd3-geo'
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from 'react'
import type { Locations, ProvinceId } from '../../api/types'
import { useElementWidth } from '../../hooks/useElementWidth'
import { PROVINCE_NAME_KO, SOURCE_LABELS } from '../../lib/constants'
import { fmtInt, fmtKrwPeriod, fmtPct } from '../../lib/format'
import { provinceGeo, type ProvinceFeature, type ProvinceProps } from '../../lib/geo'
import { ACCENT, INK, MAP_STROKE } from '../../lib/palette'
import { useLive } from '../../state/live'
import { TooltipBox } from '../ui/ChartParts'
import { FIT_LON_RANGE, LABEL_SPOTS } from './mapLabels'
import type { MapScale } from './mapScale'

type ProvinceRow = Locations['provinces'][number]

/** The mainland + Jeju without the far islands, used only to fit the projection. */
const FIT_GEO: FeatureCollection<MultiPolygon, ProvinceProps> = {
  type: 'FeatureCollection',
  features: provinceGeo.features.map((f) => {
    const polygons = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates
    const kept = polygons.filter((p) => {
      const [lon] = geoCentroid({ type: 'Polygon', coordinates: p })
      return lon >= FIT_LON_RANGE[0] && lon <= FIT_LON_RANGE[1]
    })
    return { ...f, geometry: { type: 'MultiPolygon', coordinates: kept } } as Feature<MultiPolygon, ProvinceProps>
  }),
}

/** Large provinces first, so metros (Seoul inside Gyeonggi-do) are drawn on top. */
const FEATURES: ProvinceFeature[] = [...provinceGeo.features].sort((a, b) => geoArea(b) - geoArea(a))

const PAD = 12
const LABEL_FONT = 12

/** Counts animate to their new value after a live update. */
function AnimatedCount({ value }: { value: number }) {
  const [shown, setShown] = useState(value)
  const from = useRef(value)
  useEffect(() => {
    const start = performance.now()
    const begin = from.current
    if (begin === value) return
    let frame = 0
    const tick = (t: number) => {
      const k = Math.min(1, (t - start) / 700)
      const eased = 1 - (1 - k) ** 3
      const next = Math.round(begin + (value - begin) * eased)
      from.current = next
      setShown(next)
      if (k < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [value])
  return <>{fmtInt(shown)}</>
}

export interface KoreaMapProps {
  locations: Locations
  scale: MapScale
  selected: ProvinceId | null
  onSelect: (id: ProvinceId | null) => void
  maxHeight?: number
}

export function KoreaMap({ locations, scale, selected, onSelect, maxHeight = 720 }: KoreaMapProps) {
  const [ref, width] = useElementWidth()
  const { pulses } = useLive()
  const [hover, setHover] = useState<{ id: ProvinceId; x: number; y: number } | null>(null)
  const rows = useMemo(() => new Map(locations.provinces.map((p) => [p.province as ProvinceId, p])), [locations])

  const layout = useMemo(() => {
    if (width <= 0) return null
    const unit = geoMercator().fitWidth(1000, FIT_GEO)
    const [[x0, y0], [x1, y1]] = geoPath(unit).bounds(FIT_GEO)
    const aspect = (y1 - y0) / (x1 - x0)
    const height = Math.min(maxHeight, Math.round(width * aspect))
    const projection = geoMercator().fitExtent(
      [
        [PAD, PAD],
        [width - PAD, height - PAD],
      ],
      FIT_GEO,
    )
    const path = geoPath(projection)
    const shapes = FEATURES.map((f) => {
      const id = f.properties.id
      const spot = LABEL_SPOTS[id]
      const ads = rows.get(id)?.ads ?? 0
      const text = fmtInt(ads)
      const [[bx0, by0], [bx1, by1]] = path.bounds(f)
      const fits = !spot.origin && bx1 - bx0 >= text.length * 7.2 + 10 && by1 - by0 >= LABEL_FONT + 8
      const at = projection(spot.at) ?? [0, 0]
      const outside = spot.outside && !fits ? projection(spot.outside) : null
      const origin = outside ? (projection(spot.origin ?? spot.at) ?? at) : null
      return { id, d: path(f) ?? '', label: outside ?? at, outside: outside !== null, origin, centroid: path.centroid(f) }
    })
    return { height, shapes }
  }, [width, maxHeight, rows])

  const placed = locations.provinces.reduce((s, p) => s + p.ads, 0)

  const toggle = (id: ProvinceId) => onSelect(selected === id ? null : id)
  const onKey = (e: KeyboardEvent, id: ProvinceId) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      toggle(id)
    }
  }
  const track = (e: MouseEvent, id: ProvinceId) => {
    const box = ref.current?.getBoundingClientRect()
    if (box) setHover({ id, x: e.clientX - box.left, y: e.clientY - box.top })
  }

  const hovered = hover ? rows.get(hover.id) : undefined

  return (
    <div ref={ref} className="relative w-full">
      {layout && (
        <svg
          width={width}
          height={layout.height}
          viewBox={`0 0 ${width} ${layout.height}`}
          className="mx-auto block touch-manipulation select-none"
          role="group"
          aria-label="Map of job ads per province"
          onClick={() => onSelect(null)}
        >
          {layout.shapes.map((s) => {
            const ads = rows.get(s.id)?.ads ?? 0
            const dimmed = selected !== null && selected !== s.id
            return (
              <path
                key={s.id}
                d={s.d}
                data-region={s.id}
                tabIndex={0}
                role="button"
                aria-pressed={selected === s.id}
                aria-label={`${s.id} (${PROVINCE_NAME_KO[s.id]}): ${fmtInt(ads)} ads`}
                fill={scale.fill(ads)}
                stroke={MAP_STROKE}
                strokeWidth={1}
                strokeLinejoin="round"
                className="cursor-pointer outline-none transition-[opacity,filter] duration-200 hover:brightness-95 focus-visible:brightness-90"
                opacity={dimmed ? 0.6 : 1}
                onClick={(e) => {
                  e.stopPropagation()
                  toggle(s.id)
                }}
                onKeyDown={(e) => onKey(e, s.id)}
                onMouseMove={(e) => track(e, s.id)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover({ id: s.id, x: s.centroid[0], y: s.centroid[1] })}
                onBlur={() => setHover(null)}
              />
            )
          })}

          {/* Hover and selection outlines on top of every fill. */}
          {layout.shapes
            .filter((s) => s.id === hover?.id && s.id !== selected)
            .map((s) => (
              <path key={`hover-${s.id}`} d={s.d} fill="none" stroke={INK} strokeWidth={1.25} pointerEvents="none" />
            ))}
          {layout.shapes
            .filter((s) => s.id === selected)
            .map((s) => (
              <path key={`sel-${s.id}`} d={s.d} fill="none" stroke={ACCENT} strokeWidth={3} strokeLinejoin="round" pointerEvents="none" />
            ))}
          {layout.shapes
            .filter((s) => s.id in pulses)
            .map((s) => (
              <path
                key={`pulse-${s.id}-${pulses[s.id]}`}
                d={s.d}
                fill="none"
                stroke={ACCENT}
                pointerEvents="none"
                className="animate-region-pulse"
              />
            ))}

          {/* Counts: inside the province, or outside with a leader line for small metros. */}
          {layout.shapes.map((s) => {
            const ads = rows.get(s.id)?.ads ?? 0
            const dimmed = selected !== null && selected !== s.id
            return (
              <g key={`label-${s.id}`} pointerEvents="none" opacity={dimmed ? 0.55 : 1} className="transition-opacity">
                {s.outside && s.origin && (
                  <>
                    <line x1={s.origin[0]} y1={s.origin[1]} x2={s.label[0]} y2={s.label[1]} stroke="#94a3b8" strokeWidth={0.75} />
                    <circle cx={s.origin[0]} cy={s.origin[1]} r={1.75} fill="#475569" />
                  </>
                )}
                <text
                  x={s.label[0]}
                  y={s.label[1]}
                  dy="0.35em"
                  textAnchor="middle"
                  fontSize={LABEL_FONT}
                  fontWeight={650}
                  fill={s.outside ? INK : scale.ink(ads)}
                  stroke={s.outside ? '#ffffff' : 'none'}
                  strokeWidth={s.outside ? 3.5 : 0}
                  paintOrder="stroke"
                  style={{ fontVariantNumeric: 'tabular-nums' }}
                >
                  <AnimatedCount value={ads} />
                </text>
              </g>
            )
          })}
        </svg>
      )}
      {!layout && <div style={{ height: 480 }} />}

      {hover && hovered && (
        <div
          className="pointer-events-none absolute z-20"
          style={{
            left: Math.min(hover.x + 14, Math.max(0, width - 230)),
            top: Math.max(0, hover.y - 10),
          }}
        >
          <ProvinceTooltip row={hovered} placed={placed} />
        </div>
      )}
    </div>
  )
}

function ProvinceTooltip({ row, placed }: { row: ProvinceRow; placed: number }) {
  const sources = Object.entries(row.by_source) as [keyof ProvinceRow['by_source'], number][]
  const [topSource, topCount] = sources.reduce((a, b) => (b[1] > a[1] ? b : a))
  return (
    <TooltipBox
      title={
        <>
          {row.province} <span className="font-normal text-slate-500">{row.name_ko}</span>
        </>
      }
      rows={[
        { key: 'ads', label: 'Unique ads', value: fmtInt(row.ads) },
        { key: 'share', label: 'Share of placed ads', value: placed ? fmtPct(row.ads / placed) : '—' },
        { key: 'pay', label: 'Median daily pay', value: fmtKrwPeriod(row.median_daily_pay, 'daily') },
      ]}
      footer={row.ads > 0 && topCount > 0 ? `Mostly located by: ${SOURCE_LABELS[topSource].toLowerCase()}` : 'No ads in this period'}
    />
  )
}
