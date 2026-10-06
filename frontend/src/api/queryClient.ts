// The app's single react-query client and the query-key helpers shared by hooks and the live layer.
import { QueryClient } from '@tanstack/react-query'
import type { Filters } from './types'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      staleTime: 30_000,
    },
  },
})

/** Every stats query key starts with 'stats' so one invalidate refreshes them all on a live update. */
export const queryKeys = {
  health: ['health'] as const,
  stats: ['stats'] as const,
  meta: ['stats', 'meta'] as const,
  overview: (f: Filters) => ['stats', 'overview', f] as const,
  locations: (f: Filters) => ['stats', 'locations', f] as const,
  region: (id: string | null, f: Filters) => ['stats', 'region', id, f] as const,
  feed: (opts: { limit: number; province: string | null }, f: Filters) => ['stats', 'feed', opts, f] as const,
  pay: (f: Filters) => ['stats', 'pay', f] as const,
  jobs: (f: Filters) => ['stats', 'jobs', f] as const,
  posts: (f: Filters) => ['stats', 'posts', f] as const,
  groups: (f: Filters) => ['stats', 'groups', f] as const,
}

/** Refetch every stats query (active ones immediately, inactive ones on next mount). */
export function invalidateStats(client: QueryClient = queryClient): Promise<void> {
  return client.invalidateQueries({ queryKey: queryKeys.stats })
}
