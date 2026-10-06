// Choropleth classes: nice log-scale thresholds (1-2-5 steps) from the data, mapped onto the 7-step blue ramp.
import { MAP_RAMP, MAP_ZERO, mapLabelInk } from '../../lib/palette'

/** Ascending lower bounds of every class above the first (at most maxClasses - 1 of them). */
export function logThresholds(values: number[], maxClasses = MAP_RAMP.length): number[] {
  const positive = values.filter((v) => v > 0)
  if (positive.length < 2) return []
  const lo = Math.min(...positive)
  const hi = Math.max(...positive)
  if (lo === hi) return []
  const nice: number[] = []
  for (let e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) for (const m of [1, 2, 5]) nice.push(m * 10 ** e)
  const candidates = nice.filter((v) => v > lo && v <= hi)
  const wanted = maxClasses - 1
  if (candidates.length <= wanted) return candidates
  const [a, b] = [Math.log10(lo), Math.log10(hi)]
  const picks = new Set<number>()
  for (let i = 1; i <= wanted; i++) {
    const target = a + ((b - a) * i) / (wanted + 1)
    const best = candidates.reduce((x, y) => (Math.abs(Math.log10(y) - target) < Math.abs(Math.log10(x) - target) ? y : x))
    picks.add(best)
  }
  return [...picks].sort((x, y) => x - y)
}

export interface MapScale {
  thresholds: number[]
  /** Ramp step (0..6) of a count, or -1 for zero. */
  step: (count: number) => number
  fill: (count: number) => string
  ink: (count: number) => string
  /** One entry per class for the legend. */
  classes: { step: number; color: string; from: number; to: number | null }[]
}

export function mapScale(values: number[]): MapScale {
  const thresholds = logThresholds(values)
  const count = thresholds.length + 1
  const rampStep = (cls: number) => (count === 1 ? 3 : Math.round((cls * (MAP_RAMP.length - 1)) / (count - 1)))
  const classOf = (v: number) => thresholds.filter((t) => v >= t).length
  const step = (v: number) => (v > 0 ? rampStep(classOf(v)) : -1)
  const lows = [1, ...thresholds]
  return {
    thresholds,
    step,
    fill: (v) => (v > 0 ? MAP_RAMP[step(v)] : MAP_ZERO),
    ink: (v) => (v > 0 ? mapLabelInk(step(v)) : '#64748b'),
    classes: lows.map((from, i) => ({ step: rampStep(i), color: MAP_RAMP[rampStep(i)], from, to: thresholds[i] ?? null })),
  }
}
