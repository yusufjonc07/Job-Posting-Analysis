// Shared design tokens for charts and the map (hex values; mirrored as Tailwind colors in index.css @theme).
import type { LocationSource, Period } from '../api/types'

/** Categorical series in fixed order (validated colorblind-safe); use slot 4 only if unavoidable. Never cycle. */
export const SERIES = ['#2a78d6', '#eb6834', '#1baf7a', '#eda100'] as const

/** De-emphasis / "other" / unknown grey. */
export const CONTEXT = '#c3c2b7'

/** Pay periods are always hourly = blue, daily = orange, monthly = aqua. */
export const PERIOD_COLORS: Record<Period, string> = { hourly: SERIES[0], daily: SERIES[1], monthly: SERIES[2] }

/** Location sources are always address = blue, text = orange, group = aqua, unknown = grey. */
export const SOURCE_COLORS: Record<LocationSource, string> = {
  address: SERIES[0],
  text: SERIES[1],
  group: SERIES[2],
  unknown: CONTEXT,
}

/** Direct posts = blue, forwarded (bot) posts = orange. */
export const DIRECT_FORWARDED = { direct: SERIES[0], forwarded: SERIES[1] } as const

/** Writing scripts (Posts page): Latin = blue, Cyrillic = orange, Hangul = aqua. */
export const SCRIPT_COLORS = { Latin: SERIES[0], Cyrillic: SERIES[1], Hangul: SERIES[2] } as const

/** Map sequential ramp, light → dark (more jobs = darker). */
export const MAP_RAMP = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'] as const
/** Fill for provinces with zero ads. */
export const MAP_ZERO = '#eef2f7'
/** Province outline on the map (surface-coloured gap between fills). */
export const MAP_STROKE = '#ffffff'
/** Ink for a label drawn on a ramp step: white on the 4 darkest steps, slate-900 otherwise. */
export function mapLabelInk(step: number): string {
  return step >= MAP_RAMP.length - 4 ? '#ffffff' : INK
}

/** Hairline solid gridlines (never dashed). */
export const GRID = '#e2e8f0'
/** Axis baseline. */
export const AXIS = '#cbd5e1'
/** Primary text (slate-900). */
export const INK = '#0f172a'
/** Secondary text (slate-600). */
export const INK_2 = '#475569'
/** Muted text, axis ticks (slate-500). */
export const MUTED = '#64748b'
/** UI accent (blue-600) — for controls and selection, not for data series. */
export const ACCENT = '#2563eb'
/** Reserved status colours (always paired with an icon + label). */
export const STATUS = { good: '#0ca30c', warning: '#fab219', serious: '#ec835a', critical: '#d03b3b' } as const
/** Delta text colours on light surfaces: up-good / down-bad. */
export const DELTA_GOOD = '#047857'
export const DELTA_BAD = '#be123c'
