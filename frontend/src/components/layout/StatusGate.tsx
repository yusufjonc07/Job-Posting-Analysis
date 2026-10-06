// Full-page states before any data can show: store still loading (with progress) or backend unreachable.
import { LoaderCircle, WifiOff } from 'lucide-react'
import type { ReactNode } from 'react'
import { useHealth } from '../../api/hooks'
import { useLive } from '../../state/live'

const START_COMMAND = '.venv/bin/uvicorn src.api.main:app --port 8000'

export function StatusGate({ children }: { children: ReactNode }) {
  const { status, progress } = useLive()
  const health = useHealth()
  if (status === 'loading') {
    const pct = Math.round((progress ?? 0) * 100)
    return (
      <Screen icon={<LoaderCircle className="size-7 animate-spin text-blue-600" aria-hidden />} title="Loading the job ads…">
        <p>The server is reading the Telegram exports. This takes about half a minute the first time, then it starts from a cache.</p>
        <div className="mx-auto mt-5 h-2 w-64 overflow-hidden rounded-full bg-blue-900/10">
          <div className="h-full rounded-full bg-blue-600 transition-[width] duration-500" style={{ width: `${pct}%` }} />
        </div>
        <div className="mt-2 text-xs text-slate-500 tabular-nums">{pct}%</div>
      </Screen>
    )
  }
  if (status === 'offline' && !health.data) {
    return (
      <Screen icon={<WifiOff className="size-7 text-rose-500" aria-hidden />} title="The API server is not running">
        <p>Start it from the repository root, then this page connects by itself:</p>
        <code className="mt-3 inline-block rounded-lg bg-slate-900/[0.06] px-3 py-1.5 text-[13px] text-slate-800">{START_COMMAND}</code>
      </Screen>
    )
  }
  if (!health.data && status === 'connecting') {
    return <Screen icon={<LoaderCircle className="size-7 animate-spin text-blue-600" aria-hidden />} title="Connecting…" />
  }
  return <>{children}</>
}

function Screen({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="glass mx-auto mt-6 flex max-w-xl flex-col items-center px-8 py-14 text-center">
      {icon}
      <h2 className="mt-4 text-lg font-semibold text-slate-900">{title}</h2>
      {children && <div className="mt-2 text-[13px] leading-6 text-slate-600">{children}</div>}
    </div>
  )
}
