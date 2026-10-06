// Right sidebar on every page except /map: the newest unique ads (current filters); new arrivals slide in on top.
import { useEffect, useState } from 'react'
import { useFeed } from '../../api/hooks'
import { useNow } from '../../hooks/useNow'
import { plural } from '../../lib/format'
import { useFilters } from '../../state/filters'
import { LiveBadge } from '../layout/LiveBadge'
import { Skeleton } from '../ui/Skeleton'
import { EmptyState, ErrorState } from '../ui/States'
import { FeedItemCard } from './FeedItemCard'

interface Tracking {
  key: string
  base: Set<string>
  fresh: Set<string>
}

export function LiveFeed() {
  const feed = useFeed({ limit: 20 })
  const { filters } = useFilters()
  const now = useNow(15_000)
  const key = JSON.stringify(filters)
  const items = feed.data?.items
  const settled = items !== undefined && !feed.isPlaceholderData

  // Items that were not in the first answer for these filters arrived live: highlight and count them.
  const [track, setTrack] = useState<Tracking | null>(null)
  useEffect(() => {
    if (!settled || !items) return
    setTrack((t) => {
      if (!t || t.key !== key) return { key, base: new Set(items.map((i) => i.id)), fresh: new Set() }
      const added = items.filter((i) => !t.base.has(i.id) && !t.fresh.has(i.id))
      return added.length ? { ...t, fresh: new Set([...t.fresh, ...added.map((i) => i.id)]) } : t
    })
  }, [items, key, settled])
  const fresh = track?.key === key ? track.fresh : new Set<string>()

  return (
    <section aria-label="Live feed" className="glass flex h-full flex-col overflow-hidden">
      <header className="border-b border-slate-900/[0.06] px-4 pt-4 pb-3">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-[15px] font-semibold text-slate-900">Latest ads</h2>
          <LiveBadge />
        </div>
        <p className="mt-0.5 text-xs text-slate-500">
          Newest unique ads for the current filters
          {fresh.size > 0 && <span className="font-medium text-blue-700"> · {plural(fresh.size, 'new ad')} since you opened</span>}
        </p>
      </header>
      <div className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
        {items === undefined ? (
          feed.isError ? (
            <ErrorState error={feed.error} onRetry={() => void feed.refetch()} />
          ) : (
            Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-28 w-full rounded-xl" />)
          )
        ) : items.length === 0 ? (
          <EmptyState title="No ads in this period">Try a longer period or another source.</EmptyState>
        ) : (
          items.map((item) => <FeedItemCard key={item.id} item={item} now={now} fresh={fresh.has(item.id)} />)
        )}
      </div>
    </section>
  )
}
