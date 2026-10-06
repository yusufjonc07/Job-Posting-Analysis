// Typed fetch client for every backend endpoint (spec §4). All paths are relative: /api is proxied in dev.
import type {
  Feed,
  Filters,
  Groups,
  Health,
  Jobs,
  Locations,
  Meta,
  Overview,
  Pay,
  Posts,
  Region,
} from './types'

export const API_BASE = '/api'

/** What went wrong: backend still loading (503), unreachable (network / proxy 502/504), or any other HTTP error. */
export type ApiErrorKind = 'loading' | 'offline' | 'http'

/** Error thrown by every client call; `status` is 0 for network failures. */
export class ApiError extends Error {
  readonly status: number
  readonly kind: ApiErrorKind
  readonly detail: string | null
  /** Store loading progress 0..1 (only for kind 'loading'). */
  readonly progress: number | null

  constructor(status: number, kind: ApiErrorKind, message: string, detail: string | null = null, progress: number | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.kind = kind
    this.detail = detail
    this.progress = progress
  }
}

/** True when the backend answered 503 because the store is still loading. */
export const isLoadingError = (e: unknown): e is ApiError => e instanceof ApiError && e.kind === 'loading'
/** True when the backend could not be reached at all. */
export const isOfflineError = (e: unknown): e is ApiError => e instanceof ApiError && e.kind === 'offline'
/** True for a 404 (e.g. unknown region id). */
export const isNotFoundError = (e: unknown): e is ApiError => e instanceof ApiError && e.status === 404

type Params = Record<string, string | number | boolean | null | undefined>

/** Common filters → query params; defaults are omitted so URLs stay short. */
export function filterParams(f: Filters): Params {
  return {
    days: f.days,
    source: f.source === 'all' ? undefined : f.source,
    basis: f.basis === 'all' ? undefined : f.basis,
  }
}

/** Builds `/api/<path>?a=1&b=2`, skipping null/undefined values. */
export function apiUrl(path: string, params: Params = {}): string {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  const q = qs.toString()
  return `${API_BASE}${path}${q ? `?${q}` : ''}`
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

/** GET a JSON endpoint and throw a classified ApiError on failure. */
export async function apiGet<T>(path: string, params: Params = {}, signal?: AbortSignal): Promise<T> {
  let res: Response
  try {
    res = await fetch(apiUrl(path, params), { signal, headers: { Accept: 'application/json' } })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(0, 'offline', 'Backend unreachable')
  }
  const body = await readBody(res)
  if (res.ok) return body as T

  const obj = body && typeof body === 'object' ? (body as Record<string, unknown>) : {}
  const detail = typeof obj.detail === 'string' ? obj.detail : typeof body === 'string' ? body : null
  if (res.status === 503 && obj.status === 'loading') {
    const progress = typeof obj.progress === 'number' ? obj.progress : null
    throw new ApiError(503, 'loading', 'Data is still loading', detail, progress)
  }
  if (res.status === 502 || res.status === 504 || obj.offline === true) {
    throw new ApiError(res.status, 'offline', 'Backend unreachable', detail)
  }
  throw new ApiError(res.status, 'http', detail ?? `Request failed (${res.status})`, detail)
}

/** One function per endpoint. */
export const api = {
  health: (signal?: AbortSignal) => apiGet<Health>('/health', {}, signal),
  meta: (signal?: AbortSignal) => apiGet<Meta>('/meta', {}, signal),
  overview: (f: Filters, signal?: AbortSignal) => apiGet<Overview>('/overview', filterParams(f), signal),
  locations: (f: Filters, signal?: AbortSignal) => apiGet<Locations>('/locations', filterParams(f), signal),
  region: (province: string, f: Filters, signal?: AbortSignal) =>
    apiGet<Region>(`/regions/${encodeURIComponent(province)}`, filterParams(f), signal),
  feed: (f: Filters, opts: { limit?: number; province?: string | null } = {}, signal?: AbortSignal) =>
    apiGet<Feed>('/feed', { ...filterParams(f), limit: opts.limit, province: opts.province ?? undefined }, signal),
  pay: (f: Filters, signal?: AbortSignal) => apiGet<Pay>('/pay', filterParams(f), signal),
  jobs: (f: Filters, signal?: AbortSignal) => apiGet<Jobs>('/jobs', filterParams(f), signal),
  posts: (f: Filters, signal?: AbortSignal) => apiGet<Posts>('/posts', filterParams(f), signal),
  groups: (f: Filters, signal?: AbortSignal) => apiGet<Groups>('/groups', filterParams(f), signal),
}

/** URL of the server-sent events stream. */
export const EVENTS_URL = `${API_BASE}/events`
