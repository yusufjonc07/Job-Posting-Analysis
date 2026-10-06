// API contract types — mirror of spec §4 (webapp_spec.md). Do not rename fields.

export type Period = 'hourly' | 'daily' | 'monthly'
export type Granularity = 'day' | 'week' | 'month' // days ≤ 31 → day, ≤ 180 → week, else month (also for 'all')
export type LocationSource = 'address' | 'text' | 'group' | 'unknown'

/** The 17 map provinces, in the backend's fixed order. */
export const PROVINCE_IDS = [
  'Seoul',
  'Busan',
  'Daegu',
  'Incheon',
  'Gwangju',
  'Daejeon',
  'Ulsan',
  'Sejong',
  'Gyeonggi-do',
  'Gangwon-do',
  'Chungcheongbuk-do',
  'Chungcheongnam-do',
  'Jeollabuk-do',
  'Jeollanam-do',
  'Gyeongsangbuk-do',
  'Gyeongsangnam-do',
  'Jeju-do',
] as const
export type ProvinceId = (typeof PROVINCE_IDS)[number]

// ---- common filters (query params of every stats endpoint) ----

export type SourceFilter = 'all' | 'direct' | 'forwarded'
export type BasisFilter = 'all' | 'post'
export interface Filters {
  /** Only ads whose representative date ≥ now − days; undefined = all time. */
  days?: number
  source: SourceFilter
  basis: BasisFilter
}

// ---- GET /api/health (never 503) ----

/** The Telegram listener that writes new posts as Telegram pushes them (managed = started by the API). */
export interface ListenerStatus {
  state: 'disabled' | 'starting' | 'connecting' | 'catching_up' | 'listening' | 'restarting' | 'login_required' | 'external'
  managed: boolean
  restarts: number
  messages_saved: number
  /** Messages read so far while catching up after a start. */
  catch_up_read?: number
  /** Groups followed besides the source: pushed live (joined), checked periodically (not joined), skipped (private). */
  groups?: { live: number; polled: number; skipped: number } | null
  last_message_at: string | null
}
/** A Telegram account, as Telegram reports it at login. */
export interface TelegramUser {
  id: number
  first_name?: string
  last_name?: string
  username?: string
  photo_url?: string
}

/** GET /api/auth/me: whether login is needed for province and group data, and who is logged in. */
export interface AuthState {
  required: boolean
  enabled: boolean
  user: TelegramUser | null
  allowed: boolean
  bot_username: string | null
  widget_domain: string | null
}

export interface LoginLink {
  token: string
  url: string
  expires_in: number
}

export interface LoginLinkStatus extends Partial<AuthState> {
  status: 'pending' | 'done' | 'expired' | 'unknown' | 'forbidden'
}

export interface Health {
  status: 'loading' | 'ready'
  progress: number /*0..1*/
  version: number
  posts: number
  unique_ads: number
  files: number
  last_update: string | null /*ISO time of last ingest that added rows*/
  last_post: string | null /*max post date*/
  listener?: ListenerStatus
}

// ---- GET /api/meta ----

export interface Meta {
  version: number
  provinces: { id: string; name_ko: string }[]
  date_min: string | null
  date_max: string | null
  groups: number
  /** Every message with text, of every kind; only job offers are used anywhere else. */
  messages?: number
  /** Messages that are not job offers, per kind (job_seeker, cargo, travel, sale, service, chat). */
  excluded?: Record<string, number>
}

// ---- GET /api/overview ----

export interface Overview {
  version: number
  kpis: {
    unique_ads: number
    posts: number /*rows in window incl. reposts*/
    repost_share: number /*1 - unique/posts*/
    last_24h: number
    last_7d: number
    prev_7d: number /*unique ads, ignore `days`, respect source*/
    salary_share: number
    median_pay: Record<Period, number | null>
    located_share: number /*province from post text*/
    forwarded_share: number
  }
  volume: { granularity: Granularity; points: { t: string /*bucket start, ISO date*/; direct: number; forwarded: number }[] }
  top_provinces: { province: string; ads: number }[] /*top 5, respects basis*/
}

// ---- GET /api/locations ----

export interface Locations {
  version: number
  total: number
  provinces: {
    province: string
    name_ko: string
    ads: number
    share: number /*of placed ads*/
    by_source: { address: number; text: number; group: number }
    median_daily_pay: number | null /*≥10 daily-pay ads*/
  }[] /*all 17, zeros included*/
  unplaced: { nationwide: number; unknown: number; group_fallback: number }
  sources: Record<LocationSource, number>
}

// ---- GET /api/regions/{province} (404 {"detail": "Unknown region"} if not one of the 17 ids) ----

export interface Region {
  version: number
  province: string
  name_ko: string
  ads: number
  rank: number /*1-based among 17*/
  share: number
  trend: { granularity: Granularity; points: { t: string; ads: number }[] }
  by_source: { address: number; text: number; group: number }
  cities: { city: string /*'' → 'Unspecified'*/; ads: number }[] /*top 10*/
  pay: { period: Period; ads: number; median: number | null; q1: number | null; q3: number | null }[] /*all 3 periods*/
  occupations: { name: string; ads: number }[]
  visas: { name: string; ads: number }[]
  scripts: { Latin: number; Cyrillic: number; Hangul: number } /*shares*/
  groups: {
    group_id: number | null
    source_file: string
    title: string
    home_province: string | null
    ads: number
    last_post: string | null
  }[] /*top 10 groups contributing ads to this region*/
  latest: FeedItem[] /*5 newest*/
}

// ---- GET /api/feed?limit=20&province=Seoul (limit 1..100, province optional, plus common filters) ----

export interface FeedItem {
  id: string
  date: string
  group_title: string
  province: string | null
  city: string | null
  location_source: LocationSource
  salary: { amount: number; period: Period } | null
  occupations: string[]
  visas: string[]
  excerpt: string
  is_forwarded: boolean
  repost_count: number
}
export interface Feed {
  version: number
  items: FeedItem[] // newest first by representative date
}

// ---- GET /api/pay ----

export interface Pay {
  version: number
  periods: {
    period: Period
    ads: number
    median: number | null
    q1: number | null
    q3: number | null
    bin_width: number
    bins: { x0: number; x1: number; ads: number }[]
  }[] /* bins span src.utils.salary.PERIOD_RANGES; widths hourly 500, daily 10_000, monthly 100_000 */
  trend: {
    period: Period
    points: { t: string; quarter: string /*'2025Q3'*/; ads: number; median: number | null /*null if ads < 30*/ }[]
  }[] /* full quarter range from first to last quarter with data; current (incomplete) quarter excluded */
  by_province: { province: string; ads: number; median: number; q1: number; q3: number }[] /*daily pay, provinces with ≥ 30 ads, sorted by median desc*/
}

// ---- GET /api/jobs ----

export interface Jobs {
  version: number
  named_share: number
  visa_share: number
  occupations: { name: string; ads: number; share: number }[] /*all 8, desc*/
  visas: { name: string; ads: number; share: number }[] /*desc, only > 0*/
  matrix: {
    provinces: string[] /*top 10 by ads*/
    occupations: string[]
    cells: number[][] /*[province][occupation] ad counts*/
  }
}

// ---- GET /api/posts ----

export type PostFlagKey = 'is_forwarded' | 'has_phone' | 'has_salary' | 'is_filled' | 'has_url'
export type RepostBucket = 'once' | '2 times' | '3–5 times' | '6–20 times' | '21–100 times' | '100+ times'

export interface Posts {
  version: number
  scripts: { year: number; Latin: number; Cyrillic: number; Hangul: number }[] /*shares per KST year*/
  flags: { key: PostFlagKey; label: string; share: number }[]
  length: { median: number; bins: { x0: number; x1: number; ads: number }[] /*log-spaced, 1..10_000 chars, ~40 bins*/ }
  reposts: { bucket: RepostBucket; unique_ads: number; posts: number; share_of_posts: number }[]
}

// ---- GET /api/groups ----

export interface GroupRow {
  group_id: number | null
  source_file: string
  title: string /*csv title, else most common parse_post group_name in the file, else derived from file name*/
  home_province: string | null
  home_city: string | null
  posts: number
  unique_ads: number
  forwarded_share: number
  placed_from_post_share: number /*share of its ads located from post text*/
  first_post: string | null
  last_post: string | null
}
export interface Groups {
  version: number
  groups: GroupRow[] /*desc by unique_ads*/
}

// ---- GET /api/events (SSE) ----

/** `event: hello` — sent once on connect. */
export interface HelloEvent {
  version: number
  status: 'loading' | 'ready'
}
/** `event: status` carries a full Health object (~1/s while loading; once when ready). */
export type StatusEvent = Health
/** `event: update` — new rows were ingested. */
export interface UpdateEvent {
  version: number
  added_posts: number
  added_ads: number
  posts: number
  unique_ads: number
  at: string /*ISO*/
  provinces: Record<string, number> /*new unique ads per province*/
}

/** Body of a 503 answered by stats endpoints while the store is loading. */
export interface LoadingBody {
  status: 'loading'
  progress: number
}
