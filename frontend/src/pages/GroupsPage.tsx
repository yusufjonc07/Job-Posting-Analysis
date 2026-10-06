// /groups: summary tiles, the 12 most active groups and a searchable, sortable table of every group.
import { Search } from 'lucide-react'
import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { useGroups } from '../api/hooks'
import type { GroupRow } from '../api/types'
import { BarList } from '../components/ui/BarList'
import { Card } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Skeleton } from '../components/ui/Skeleton'
import { StatTile } from '../components/ui/StatTile'
import { QueryView } from '../components/ui/States'
import { isProvinceId } from '../hooks/useSelectedRegion'
import { useNow } from '../hooks/useNow'
import { fmtDate, fmtInt, fmtPct, fmtRelative } from '../lib/format'
import { useLinkTo } from '../lib/links'
import { SERIES } from '../lib/palette'

export function GroupsPage() {
  const query = useGroups()
  return (
    <QueryView
      query={query}
      skeleton={
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-24 rounded-2xl" />
            ))}
          </div>
          <Skeleton className="h-96 rounded-2xl" />
        </div>
      }
    >
      {(data, stale) => <GroupsView groups={data.groups} stale={stale} />}
    </QueryView>
  )
}

function GroupsView({ groups, stale }: { groups: GroupRow[]; stale: boolean }) {
  const total = groups.reduce((s, g) => s + g.unique_ads, 0)
  const withHome = groups.filter((g) => g.home_province && g.home_province !== 'Nationwide').length
  const nationwide = groups.filter((g) => g.home_province === 'Nationwide').reduce((s, g) => s + g.unique_ads, 0)
  const top = groups[0]
  const active = groups.filter((g) => g.unique_ads > 0).length

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 2xl:grid-cols-4">
        <StatTile label="Telegram groups" value={fmtInt(groups.length)} sub={`${fmtInt(active)} with ads in this period`} />
        <StatTile label="With a home province" value={fmtInt(withHome)} sub="their ads can fall back to it" />
        <StatTile label="Ads from nationwide groups" value={fmtPct(total ? nationwide / total : 0)} sub="cannot be placed by group" />
        <StatTile label="Most active group" value={<span className="text-lg leading-8" title={top?.title}>{top && top.unique_ads > 0 ? top.title : '—'}</span>} sub={top ? `${fmtInt(top.unique_ads)} unique ads` : undefined} />
      </div>
      <Card title="Most active groups" subtitle="Unique ads in this period (an ad posted in several groups counts for the first one)" stale={stale}>
        <BarList
          color={SERIES[0]}
          className="grid gap-x-8 gap-y-2.5 md:grid-cols-2"
          items={groups
            .filter((g) => g.unique_ads > 0)
            .slice(0, 12)
            .map((g) => ({ key: g.source_file, label: g.title, value: g.unique_ads }))}
        />
      </Card>
      <GroupsTable groups={groups} total={total} stale={stale} />
    </div>
  )
}

function GroupsTable({ groups, total, stale }: { groups: GroupRow[]; total: number; stale: boolean }) {
  const [search, setSearch] = useState('')
  const linkTo = useLinkTo()
  const now = useNow(60_000)
  const max = Math.max(1, ...groups.map((g) => g.unique_ads))
  const rows = useMemo(() => {
    const q = search.trim().toLowerCase()
    return q ? groups.filter((g) => `${g.title} ${g.group_id ?? ''} ${g.home_province ?? ''} ${g.home_city ?? ''}`.toLowerCase().includes(q)) : groups
  }, [groups, search])

  const columns: Column<GroupRow>[] = [
    {
      key: 'title',
      header: 'Group',
      sortValue: (g) => g.title.toLowerCase(),
      className: 'max-w-[210px]',
      cell: (g) => (
        <div className="min-w-0">
          <div className="truncate font-medium text-slate-800" title={g.title}>
            {g.title}
          </div>
          <div className="truncate text-[11px] text-slate-400 tabular-nums" title={g.source_file}>
            {g.group_id ?? g.source_file}
          </div>
        </div>
      ),
    },
    {
      key: 'home',
      header: 'Home',
      sortValue: (g) => g.home_province ?? '',
      cell: (g) =>
        g.home_province ? (
          <div className="whitespace-nowrap">
            {isProvinceId(g.home_province) ? (
              <Link to={linkTo('/map', { region: g.home_province })} className="text-slate-700 hover:text-blue-700">
                {g.home_province}
              </Link>
            ) : (
              <span className="text-slate-600">{g.home_province}</span>
            )}
            {g.home_city && g.home_city !== g.home_province && <div className="text-[11px] text-slate-400">{g.home_city}</div>}
          </div>
        ) : (
          <span className="text-slate-400">—</span>
        ),
    },
    {
      key: 'ads',
      header: 'Unique ads',
      align: 'right',
      sortValue: (g) => g.unique_ads,
      cell: (g) => (
        <div className="flex items-center justify-end gap-2">
          <span className="hidden h-1.5 w-10 rounded-r-[3px] bg-slate-900/[0.04] 2xl:block">
            <span className="block h-full rounded-r-[3px]" style={{ width: `${(g.unique_ads / max) * 100}%`, backgroundColor: SERIES[0] }} />
          </span>
          <span className="w-12 font-medium text-slate-900">{fmtInt(g.unique_ads)}</span>
        </div>
      ),
    },
    { key: 'posts', header: 'Posts', align: 'right', sortValue: (g) => g.posts, cell: (g) => fmtInt(g.posts) },
    { key: 'fwd', header: 'Fwd', title: 'Share of its ads forwarded by the bot', align: 'right', sortValue: (g) => g.forwarded_share, cell: (g) => (g.unique_ads ? fmtPct(g.forwarded_share) : '—') },
    {
      key: 'placed',
      header: 'In text',
      title: 'Share of its ads located from a place named in the post',
      align: 'right',
      sortValue: (g) => g.placed_from_post_share,
      cell: (g) => (g.unique_ads ? fmtPct(g.placed_from_post_share) : '—'),
    },
    {
      key: 'first',
      header: 'First',
      title: 'First post',
      align: 'right',
      sortValue: (g) => g.first_post ?? '',
      cell: (g) => <span className="whitespace-nowrap">{fmtDate(g.first_post, 'monthShort')}</span>,
    },
    {
      key: 'last',
      header: 'Last',
      title: 'Last post',
      align: 'right',
      sortValue: (g) => g.last_post ?? '',
      cell: (g) => (
        <span className="whitespace-nowrap" title={fmtDate(g.last_post, 'datetime')}>
          {fmtRelative(g.last_post, now)}
        </span>
      ),
    },
  ]

  return (
    <Card
      title="All groups"
      subtitle={`${fmtInt(groups.length)} groups · ${fmtInt(total)} unique ads in this period`}
      stale={stale}
      actions={
        <label className="relative block">
          <span className="sr-only">Search groups</span>
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-slate-400" aria-hidden />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search groups"
            className="h-9 w-48 rounded-xl bg-white/70 pr-3 pl-8 text-[13px] text-slate-800 shadow-sm ring-1 ring-slate-900/[0.08] outline-none ring-inset placeholder:text-slate-400 focus:ring-2 focus:ring-blue-500 md:w-64"
          />
        </label>
      }
    >
      <div className="scroll-thin max-h-[640px] overflow-auto">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(g) => g.source_file}
          initialSort={{ key: 'ads', dir: 'desc' }}
          dense
          empty={search ? `No group matches "${search}"` : 'No groups'}
        />
      </div>
    </Card>
  )
}
