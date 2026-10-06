// Number, money, date and relative-time formatters (en-US numbers, Korea time for timestamps).
import type { Granularity, Period } from '../api/types'

/** Placeholder shown for null / undefined / NaN values. */
export const DASH = '—'

const intFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
const compactFmt = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 })

const isNum = (n: number | null | undefined): n is number => typeof n === 'number' && Number.isFinite(n)

/** 31,024 */
export function fmtInt(n: number | null | undefined): string {
  return isNum(n) ? intFmt.format(n) : DASH
}

/** 1,284 below 10k, then 12.9K / 1.2M (auto-compact for stat tiles and axis ticks). */
export function fmtCompact(n: number | null | undefined): string {
  if (!isNum(n)) return DASH
  return Math.abs(n) < 10_000 ? intFmt.format(n) : compactFmt.format(n)
}

/** Share 0..1 → '77%'; digits defaults to 1 below 10% and 0 otherwise. */
export function fmtPct(share: number | null | undefined, digits?: 0 | 1): string {
  if (!isNum(share)) return DASH
  const pct = share * 100
  if (pct > 0 && pct < 0.05) return '<0.1%'
  const d = digits ?? (Math.abs(pct) < 10 && pct !== 0 ? 1 : 0)
  return `${pct.toFixed(d).replace(/\.0$/, '')}%`
}

/** Signed percentage-point or percent change: +12% / −4.5%. */
export function fmtSignedPct(change: number | null | undefined, digits?: 0 | 1): string {
  if (!isNum(change)) return DASH
  const s = fmtPct(Math.abs(change), digits)
  return change > 0 ? `+${s}` : change < 0 ? `−${s}` : s
}

/** KRW compact: 13000 → '13k', 12500 → '12.5k', 135000 → '135k', 2800000 → '2.8M'. */
export function fmtKrw(n: number | null | undefined): string {
  if (!isNum(n)) return DASH
  const a = Math.abs(n)
  const sign = n < 0 ? '−' : ''
  if (a < 1000) return `${sign}${intFmt.format(a)}`
  if (a < 1_000_000) {
    const k = a / 1000
    return `${sign}${(k < 100 ? Math.round(k * 10) / 10 : Math.round(k)).toString()}k`
  }
  const m = a / 1_000_000
  return `${sign}${(m < 100 ? Math.round(m * 10) / 10 : Math.round(m)).toString()}M`
}

/** Short suffix per pay period: '/h', '/day', '/mo'. */
export const PERIOD_SUFFIX: Record<Period, string> = { hourly: '/h', daily: '/day', monthly: '/mo' }

/** KRW compact with the period suffix: '13k/h', '135k/day', '2.8M/mo'. */
export function fmtKrwPeriod(n: number | null | undefined, period: Period): string {
  return isNum(n) ? `${fmtKrw(n)}${PERIOD_SUFFIX[period]}` : DASH
}

/** Full KRW amount: '₩135,000'. */
export function fmtKrwFull(n: number | null | undefined): string {
  return isNum(n) ? `₩${intFmt.format(n)}` : DASH
}

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/
export const KST = 'Asia/Seoul'

/** Parses an API date: 'YYYY-MM-DD' is a calendar date (UTC midnight), anything else an ISO timestamp. */
export function parseApiDate(v: string | number | Date | null | undefined): Date | null {
  if (v === null || v === undefined || v === '') return null
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? null : v
  if (typeof v === 'number') return new Date(v)
  const d = DATE_ONLY.test(v) ? new Date(`${v}T00:00:00Z`) : new Date(v)
  return Number.isNaN(d.getTime()) ? null : d
}

const dtfCache = new Map<string, Intl.DateTimeFormat>()
function dtf(opts: Intl.DateTimeFormatOptions, timeZone: string): Intl.DateTimeFormat {
  const key = `${timeZone}|${JSON.stringify(opts)}`
  let f = dtfCache.get(key)
  if (!f) {
    f = new Intl.DateTimeFormat('en-US', { ...opts, timeZone })
    dtfCache.set(key, f)
  }
  return f
}

export type DateStyle = 'day' | 'date' | 'month' | 'monthShort' | 'datetime' | 'time'
const DATE_STYLES: Record<DateStyle, Intl.DateTimeFormatOptions> = {
  day: { month: 'short', day: 'numeric' }, // Oct 3
  date: { month: 'short', day: 'numeric', year: 'numeric' }, // Oct 3, 2026
  month: { month: 'short', year: 'numeric' }, // Oct 2026
  monthShort: { month: 'short', year: '2-digit' }, // Oct 26
  datetime: { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }, // Oct 3, 09:30
  time: { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }, // 09:30
}

/** Formats an API date; calendar dates are shown as-is, timestamps in Korea time. */
export function fmtDate(v: string | number | Date | null | undefined, style: DateStyle = 'date'): string {
  const d = parseApiDate(v)
  if (!d) return DASH
  const tz = typeof v === 'string' && DATE_ONLY.test(v) ? 'UTC' : KST
  return dtf(DATE_STYLES[style], tz).format(d)
}

/** Label for a time-bucket start: day/week → 'Oct 3', month → 'Oct 2026'. */
export function fmtBucket(t: string, granularity: Granularity, short = false): string {
  if (granularity === 'month') return fmtDate(t, short ? 'monthShort' : 'month')
  return fmtDate(t, 'day')
}

/** '2025Q3' → 'Q3 2025'. */
export function fmtQuarter(q: string): string {
  const m = /^(\d{4})Q([1-4])$/.exec(q)
  return m ? `Q${m[2]} ${m[1]}` : q
}

/** 'just now', '12 s ago', '5 min ago', '3 h ago', '2 d ago', else a date. */
export function fmtRelative(v: string | number | Date | null | undefined, now: number = Date.now()): string {
  const d = parseApiDate(v)
  if (!d) return DASH
  const s = Math.round((now - d.getTime()) / 1000)
  if (s < 5) return 'just now'
  if (s < 60) return `${s} s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.floor(m / 60)
  if (h < 48) return `${h} h ago`
  const days = Math.floor(h / 24)
  if (days < 30) return `${days} d ago`
  return fmtDate(d, 'date')
}

/** Relative change cur vs prev (null when prev is 0). */
export function relChange(cur: number, prev: number): number | null {
  return prev > 0 ? (cur - prev) / prev : null
}

/** Plural helper: plural(1, 'post') → '1 post', plural(3, 'post') → '3 posts'. */
export function plural(n: number, one: string, many = `${one}s`): string {
  return `${fmtInt(n)} ${n === 1 ? one : many}`
}
