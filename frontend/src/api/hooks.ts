// React-query hooks, one per endpoint. Stats hooks read the current URL filters themselves.
import { keepPreviousData, useQuery, type UseQueryResult } from '@tanstack/react-query'
import { useFilters } from '../state/filters'
import { ApiError, api, isLoadingError, isNotFoundError, isOfflineError } from './client'
import { queryKeys } from './queryClient'
import type { Feed, Groups, Health, Jobs, Locations, Meta, Overview, Pay, Posts, Region } from './types'

/** Retry 503 "loading" for as long as the store loads; retry offline/5xx a couple of times; never retry 4xx. */
function retry(failureCount: number, error: Error): boolean {
  if (isLoadingError(error)) return failureCount < 300
  if (isNotFoundError(error)) return false
  if (error instanceof ApiError && error.kind === 'http' && error.status < 500) return false
  return failureCount < 2
}

function retryDelay(attempt: number, error: Error): number {
  if (isLoadingError(error)) return 2000
  return Math.min(1000 * 2 ** attempt, 8000)
}

/** Shared options of every stats query: keep the previous data while refetching (no skeleton flash). */
const statsOptions = {
  placeholderData: keepPreviousData,
  staleTime: 30_000,
  retry,
  retryDelay,
} as const

/**
 * GET /api/health — never 503. Polls every 1.5 s while the store loads; otherwise the live layer keeps it fresh
 * (SSE status/update events, or its fallback polling while SSE is down).
 */
export function useHealth(): UseQueryResult<Health, ApiError> {
  return useQuery<Health, ApiError>({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => api.health(signal),
    staleTime: 5_000,
    retry: (count, error) => !isOfflineError(error) && count < 1,
    retryDelay: 1000,
    // Fast while loading; otherwise every 30 s so the Telegram listener state stays current.
    refetchInterval: (q) => (q.state.data?.status === 'loading' ? 1500 : 30_000),
  })
}

/** GET /api/meta — provinces, data range, group count. */
export function useMeta(): UseQueryResult<Meta, ApiError> {
  return useQuery<Meta, ApiError>({
    queryKey: queryKeys.meta,
    queryFn: ({ signal }) => api.meta(signal),
    ...statsOptions,
    staleTime: 5 * 60_000,
  })
}

/** GET /api/overview with the current filters. */
export function useOverview(): UseQueryResult<Overview, ApiError> {
  const { filters } = useFilters()
  return useQuery<Overview, ApiError>({
    queryKey: queryKeys.overview(filters),
    queryFn: ({ signal }) => api.overview(filters, signal),
    ...statsOptions,
  })
}

/** GET /api/locations with the current filters. */
export function useLocations(): UseQueryResult<Locations, ApiError> {
  const { filters } = useFilters()
  return useQuery<Locations, ApiError>({
    queryKey: queryKeys.locations(filters),
    queryFn: ({ signal }) => api.locations(filters, signal),
    ...statsOptions,
  })
}

/**
 * GET /api/regions/{id}; disabled while id is null. Keeps the previous region's data while the next one loads,
 * so compare `data.province` with `id` if you need to dim stale content.
 */
export function useRegion(id: string | null): UseQueryResult<Region, ApiError> {
  const { filters } = useFilters()
  return useQuery<Region, ApiError>({
    queryKey: queryKeys.region(id, filters),
    queryFn: ({ signal }) => api.region(id as string, filters, signal),
    ...statsOptions,
    enabled: id !== null,
    placeholderData: id === null ? undefined : keepPreviousData,
  })
}

/** GET /api/feed — newest unique ads (limit 1..100, optional province) with the current filters. */
export function useFeed({ limit = 20, province = null }: { limit?: number; province?: string | null } = {}): UseQueryResult<
  Feed,
  ApiError
> {
  const { filters } = useFilters()
  const opts = { limit, province }
  return useQuery<Feed, ApiError>({
    queryKey: queryKeys.feed(opts, filters),
    queryFn: ({ signal }) => api.feed(filters, opts, signal),
    ...statsOptions,
  })
}

/** GET /api/pay with the current filters. */
export function usePay(): UseQueryResult<Pay, ApiError> {
  const { filters } = useFilters()
  return useQuery<Pay, ApiError>({
    queryKey: queryKeys.pay(filters),
    queryFn: ({ signal }) => api.pay(filters, signal),
    ...statsOptions,
  })
}

/** GET /api/jobs with the current filters. */
export function useJobs(): UseQueryResult<Jobs, ApiError> {
  const { filters } = useFilters()
  return useQuery<Jobs, ApiError>({
    queryKey: queryKeys.jobs(filters),
    queryFn: ({ signal }) => api.jobs(filters, signal),
    ...statsOptions,
  })
}

/** GET /api/posts with the current filters. */
export function usePosts(): UseQueryResult<Posts, ApiError> {
  const { filters } = useFilters()
  return useQuery<Posts, ApiError>({
    queryKey: queryKeys.posts(filters),
    queryFn: ({ signal }) => api.posts(filters, signal),
    ...statsOptions,
  })
}

/** GET /api/groups with the current filters. */
export function useGroups(): UseQueryResult<Groups, ApiError> {
  const { filters } = useFilters()
  return useQuery<Groups, ApiError>({
    queryKey: queryKeys.groups(filters),
    queryFn: ({ signal }) => api.groups(filters, signal),
    ...statsOptions,
  })
}
