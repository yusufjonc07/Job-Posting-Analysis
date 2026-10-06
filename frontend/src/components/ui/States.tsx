// Query states: QueryView (skeleton on first load, error with retry, dimmed previous data), ErrorState, EmptyState.
import type { UseQueryResult } from '@tanstack/react-query'
import { RotateCw, TriangleAlert } from 'lucide-react'
import type { ReactNode } from 'react'
import { isLoadingError, isOfflineError, type ApiError } from '../../api/client'

export function ErrorState({ error, onRetry }: { error: Error | null; onRetry?: () => void }) {
  const offline = isOfflineError(error)
  return (
    <div className="glass flex flex-col items-center gap-3 px-6 py-12 text-center">
      <TriangleAlert className="size-6 text-amber-500" aria-hidden />
      <div>
        <div className="font-medium text-slate-900">{offline ? 'Backend unreachable' : 'Could not load this data'}</div>
        <div className="mt-1 text-[13px] text-slate-500">{offline ? 'Is the API server running?' : (error?.message ?? 'Unknown error')}</div>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex items-center gap-1.5 rounded-lg bg-white/80 px-3 py-1.5 text-[13px] font-medium text-slate-700 shadow-sm ring-1 ring-slate-900/[0.08] hover:text-slate-900"
        >
          <RotateCw className="size-3.5" aria-hidden /> Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 px-4 py-10 text-center">
      <div className="text-[13px] font-medium text-slate-700">{title}</div>
      {children && <div className="max-w-sm text-xs text-slate-500">{children}</div>}
    </div>
  )
}

/** Renders `children(data, stale)` once data exists; the skeleton only before the first answer. */
export function QueryView<T>({
  query,
  skeleton,
  children,
}: {
  query: UseQueryResult<T, ApiError>
  skeleton: ReactNode
  children: (data: T, stale: boolean) => ReactNode
}) {
  if (query.data !== undefined) return <>{children(query.data, query.isPlaceholderData)}</>
  if (query.isError && !isLoadingError(query.error)) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />
  return <>{skeleton}</>
}
