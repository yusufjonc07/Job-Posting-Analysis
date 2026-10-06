// Left navigation: app name, the six pages, and a footer with live status, last update and data range.
import clsx from 'clsx'
import { NavLink } from 'react-router'
import { useHealth, useMeta } from '../../api/hooks'
import type { ListenerStatus } from '../../api/types'
import { useNow } from '../../hooks/useNow'
import { BOUNDARIES_CREDIT } from '../../lib/constants'
import { fmtDate, fmtInt, fmtRelative } from '../../lib/format'
import { useLinkTo } from '../../lib/links'
import { ROUTES } from '../../lib/routes'
import { useLive } from '../../state/live'
import { statusText } from './LiveBadge'

export function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="size-8 shrink-0" aria-hidden>
      <defs>
        <linearGradient id="logo-g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3b82f6" />
          <stop offset="1" stopColor="#4f46e5" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill="url(#logo-g)" />
      <rect x="8" y="17" width="4" height="7" rx="1.5" fill="#fff" opacity="0.7" />
      <rect x="14" y="12" width="4" height="12" rx="1.5" fill="#fff" opacity="0.85" />
      <rect x="20" y="8" width="4" height="16" rx="1.5" fill="#fff" />
    </svg>
  )
}

const LISTENER_LOOK: Record<ListenerStatus['state'], { dot: string; text: string }> = {
  listening: { dot: 'bg-emerald-500', text: 'Telegram: listening for new posts' },
  catching_up: { dot: 'bg-blue-500', text: 'Telegram: catching up on missed posts…' },
  connecting: { dot: 'bg-slate-400', text: 'Telegram: connecting…' },
  starting: { dot: 'bg-slate-400', text: 'Telegram: starting…' },
  restarting: { dot: 'bg-amber-500', text: 'Telegram: reconnecting…' },
  external: { dot: 'bg-slate-400', text: 'Telegram: a crawler is running separately' },
  login_required: { dot: 'bg-rose-500', text: 'Telegram: log in once with python -m src.main' },
  disabled: { dot: 'bg-slate-300', text: 'Telegram listener off' },
}

function ListenerLine({ status, now }: { status: ListenerStatus; now: number }) {
  const look = LISTENER_LOOK[status.state] ?? LISTENER_LOOK.disabled
  return (
    <div className="flex items-start gap-2 text-slate-700" title={status.managed ? 'Started by the API server' : undefined}>
      <span className={clsx('mt-1 size-2 shrink-0 rounded-full', look.dot)} aria-hidden />
      <span>
        {look.text}
        {status.state === 'catching_up' && (status.catch_up_read ?? 0) > 0 && (
          <span className="block text-slate-500">{fmtInt(status.catch_up_read ?? 0)} messages read</span>
        )}
        {status.last_message_at && <span className="block text-slate-500">last post saved {fmtRelative(status.last_message_at, now)}</span>}
      </span>
    </div>
  )
}

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const linkTo = useLinkTo()
  const live = useLive()
  const meta = useMeta()
  const health = useHealth()
  const now = useNow(5000)
  const dot = { live: 'bg-emerald-500', connecting: 'bg-slate-400', reconnecting: 'bg-amber-500', loading: 'bg-blue-500', offline: 'bg-rose-500' }[live.status]

  return (
    <nav aria-label="Main" className="glass flex h-full flex-col p-3">
      <div className="flex items-center gap-2.5 px-2 pt-1 pb-5">
        <Logo />
        <div className="min-w-0">
          <div className="truncate text-[15px] leading-5 font-semibold text-slate-900">Ish e'lonlari · Korea</div>
          <div className="truncate text-xs text-slate-500">Live job-ads dashboard</div>
        </div>
      </div>
      <ul className="space-y-0.5">
        {ROUTES.map(({ path, label, icon: Icon }) => (
          <li key={path}>
            <NavLink
              to={linkTo(path)}
              end
              onClick={onNavigate}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-2.5 rounded-xl px-3 py-2 text-[13px] font-medium transition-colors',
                  isActive ? 'bg-blue-600/10 text-blue-700' : 'text-slate-600 hover:bg-white/60 hover:text-slate-900',
                )
              }
            >
              <Icon className="size-4" aria-hidden />
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="mt-auto space-y-2 border-t border-slate-900/[0.06] px-2 pt-3 text-xs text-slate-500">
        <div className="flex items-start gap-2 text-slate-700">
          <span className={clsx('mt-1 size-2 shrink-0 rounded-full', dot)} aria-hidden />
          <span>{statusText(live.status)}</span>
        </div>
        {health.data?.listener && <ListenerLine status={health.data.listener} now={now} />}
        <div>Updated {live.lastUpdateAt ? fmtRelative(live.lastUpdateAt, now) : '—'}</div>
        {meta.data && (
          <div>
            Posts {fmtDate(meta.data.date_min, 'month')} – {fmtDate(meta.data.date_max, 'date')}
            <br />
            {fmtInt(meta.data.groups)} Telegram groups
          </div>
        )}
        <div className="text-slate-400">{BOUNDARIES_CREDIT}</div>
      </div>
    </nav>
  )
}
