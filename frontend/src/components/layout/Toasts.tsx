// Live-update toasts ("+12 new posts"), bottom centre, dismissable.
import clsx from 'clsx'
import { Sparkles, X } from 'lucide-react'
import { useLive } from '../../state/live'

export function Toasts() {
  const { toasts, dismissToast } = useLive()
  return (
    <div aria-live="polite" className="pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4">
      {toasts.map((t) => (
        <div key={t.id} className="glass-strong pointer-events-auto flex animate-toast-in items-center gap-3 rounded-2xl py-2.5 pr-2 pl-3.5">
          <Sparkles className={clsx('size-4', t.tone === 'warning' ? 'text-amber-500' : 'text-blue-600')} aria-hidden />
          <div className="text-[13px]">
            <div className="font-semibold text-slate-900">{t.title}</div>
            {t.body && <div className="text-slate-500">{t.body}</div>}
          </div>
          <button type="button" onClick={() => dismissToast(t.id)} aria-label="Dismiss" className="rounded-lg p-1 text-slate-400 hover:text-slate-700">
            <X className="size-4" aria-hidden />
          </button>
        </div>
      ))}
    </div>
  )
}
