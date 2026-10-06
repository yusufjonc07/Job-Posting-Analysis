// Page frame: blurred background, left nav, top bar + page, right sidebar (RegionPanel on /map, LiveFeed elsewhere).
// Below 1280 px both sidebars become drawers.
import clsx from 'clsx'
import { X } from 'lucide-react'
import { Suspense, useEffect, useState, type ReactNode } from 'react'
import { Outlet, useLocation } from 'react-router'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useSelectedRegion } from '../../hooks/useSelectedRegion'
import { LiveFeed } from '../live/LiveFeed'
import { RegionPanel } from '../map/RegionPanel'
import { ChartSkeleton, Skeleton } from '../ui/Skeleton'
import { Sidebar } from './Sidebar'
import { StatusGate } from './StatusGate'
import { Toasts } from './Toasts'
import { TopBar } from './TopBar'

function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden bg-gradient-to-br from-sky-50 via-blue-50 to-indigo-100">
      <div className="absolute -top-40 -left-32 size-[34rem] rounded-full bg-blue-300/30 blur-3xl" />
      <div className="absolute top-1/3 -right-40 size-[38rem] rounded-full bg-indigo-300/25 blur-3xl" />
      <div className="absolute -bottom-48 left-1/4 size-[30rem] rounded-full bg-sky-200/40 blur-3xl" />
    </div>
  )
}

function Drawer({ side, open, onClose, label, children }: { side: 'left' | 'right'; open: boolean; onClose: () => void; label: string; children: ReactNode }) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
  return (
    <div className={clsx('fixed inset-0 z-40', !open && 'pointer-events-none')} aria-hidden={!open}>
      <div className={clsx('absolute inset-0 bg-slate-900/20 transition-opacity', open ? 'opacity-100' : 'opacity-0')} onClick={onClose} />
      <div
        role="dialog"
        aria-label={label}
        className={clsx(
          'absolute top-0 flex h-full flex-col p-3 transition-transform duration-300',
          side === 'left' ? 'left-0 w-[260px]' : 'right-0 w-[min(380px,92vw)]',
          open ? 'translate-x-0' : side === 'left' ? '-translate-x-full' : 'translate-x-full',
        )}
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className={clsx('absolute top-5 z-10 rounded-lg p-1 text-slate-500 hover:text-slate-900', side === 'left' ? 'right-5' : 'left-5')}
        >
          <X className="size-4" aria-hidden />
        </button>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </div>
  )
}

/** Shown for a moment while a page's code loads. */
function PageFallback() {
  return (
    <div className="glass p-5">
      <Skeleton className="mb-4 h-5 w-48" />
      <ChartSkeleton height={320} />
    </div>
  )
}

export function AppShell() {
  const { pathname } = useLocation()
  const isMap = pathname === '/map'
  const wide = useMediaQuery('(min-width: 1280px)')
  const [region] = useSelectedRegion()
  const [navOpen, setNavOpen] = useState(false)
  const [sideOpen, setSideOpen] = useState(false)

  // On narrow screens the region details live in the drawer: open it when a region gets selected.
  const [openedFor, setOpenedFor] = useState<string | null>(null)
  if (!wide && isMap && region && region !== openedFor) {
    setOpenedFor(region)
    setSideOpen(true)
  }

  const side = isMap ? <RegionPanel /> : <LiveFeed />
  const sideLabel = isMap ? 'Region details' : 'Live feed'

  return (
    <div className="relative min-h-dvh">
      <Backdrop />
      <div className="grid min-h-dvh grid-cols-1 xl:grid-cols-[256px_minmax(0,1fr)_376px]">
        {wide ? (
          <aside className="sticky top-0 h-dvh py-3 pl-3">
            <Sidebar />
          </aside>
        ) : (
          <Drawer side="left" open={navOpen} onClose={() => setNavOpen(false)} label="Navigation">
            <Sidebar onNavigate={() => setNavOpen(false)} />
          </Drawer>
        )}
        <div className="min-w-0 px-3 py-3 xl:px-4">
          <TopBar
            sideLabel={sideLabel}
            onOpenNav={wide ? undefined : () => setNavOpen(true)}
            onOpenSide={wide ? undefined : () => setSideOpen(true)}
          />
          <main className="mt-4 pb-16">
            <StatusGate>
              <Suspense fallback={<PageFallback />}>
                <Outlet />
              </Suspense>
            </StatusGate>
          </main>
        </div>
        {wide ? (
          <aside className="sticky top-0 h-dvh py-3 pr-3">{side}</aside>
        ) : (
          <Drawer side="right" open={sideOpen} onClose={() => setSideOpen(false)} label={sideLabel}>
            {side}
          </Drawer>
        )}
      </div>
      <Toasts />
    </div>
  )
}
