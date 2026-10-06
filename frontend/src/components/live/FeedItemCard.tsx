// One ad in a feed: group, time ago, place / salary chips, excerpt, occupation and visa tags, repost info.
import clsx from 'clsx'
import { Forward, MapPin, Repeat2 } from 'lucide-react'
import { Link } from 'react-router'
import type { FeedItem } from '../../api/types'
import { isProvinceId } from '../../hooks/useSelectedRegion'
import { fmtDate, fmtKrwPeriod, fmtRelative } from '../../lib/format'
import { useLinkTo } from '../../lib/links'
import { PERIOD_COLORS } from '../../lib/palette'
import { Badge } from '../ui/Badge'

export function FeedItemCard({ item, now, fresh = false }: { item: FeedItem; now: number; fresh?: boolean }) {
  const linkTo = useLinkTo()
  const place = item.province && item.city && item.city !== item.province ? `${item.province} · ${item.city}` : item.province
  return (
    <article
      className={clsx(
        'rounded-xl px-3 py-2.5 ring-1 transition-colors ring-inset',
        fresh ? 'animate-slide-in bg-blue-50/80 ring-blue-400/40' : 'bg-white/55 ring-white/70 hover:bg-white/75',
      )}
    >
      <div className="flex items-baseline justify-between gap-2 text-[11px] leading-4">
        <span className="min-w-0 truncate font-medium text-slate-700" title={item.group_title}>
          {item.group_title}
        </span>
        <time dateTime={item.date} title={fmtDate(item.date, 'datetime')} className="shrink-0 text-slate-500 tabular-nums">
          {fmtRelative(item.date, now)}
        </time>
      </div>
      <div className="mt-1.5 flex flex-wrap gap-1">
        {place && isProvinceId(item.province) && (
          <Link to={linkTo('/map', { region: item.province })} title="Show on the map">
            <Badge tone="blue" className="hover:bg-blue-500/20">
              <MapPin className="size-3" aria-hidden />
              {place}
            </Badge>
          </Link>
        )}
        {item.salary && (
          <Badge tone="neutral" dot={PERIOD_COLORS[item.salary.period]}>
            {fmtKrwPeriod(item.salary.amount, item.salary.period)}
          </Badge>
        )}
        {item.is_forwarded && (
          <Badge tone="orange" title="Forwarded by the Ish e'lonlari bot">
            <Forward className="size-3" aria-hidden />
            Forwarded
          </Badge>
        )}
        {item.repost_count > 1 && (
          <Badge tone="neutral" title="The same ad text was posted this many times">
            <Repeat2 className="size-3" aria-hidden />
            Posted {item.repost_count}×
          </Badge>
        )}
      </div>
      <p className="mt-1.5 line-clamp-3 text-[13px] leading-5 break-words text-slate-700">{item.excerpt}</p>
      {(item.occupations.length > 0 || item.visas.length > 0) && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {item.occupations.map((o) => (
            <Badge key={o} tone="aqua">
              {o}
            </Badge>
          ))}
          {item.visas.map((v) => (
            <Badge key={v} tone="indigo">
              {v}
            </Badge>
          ))}
        </div>
      )}
    </article>
  )
}
