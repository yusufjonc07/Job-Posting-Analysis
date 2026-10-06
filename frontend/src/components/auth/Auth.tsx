// Log in with Telegram: the button, the login dialog (deep link to the bot, or the official widget on the
// bot's domain), the account box for the sidebar and the card shown instead of province / group data.
import { useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ExternalLink, LoaderCircle, Lock, LogOut, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../../api/client'
import { useAuth } from '../../api/hooks'
import type { LoginLink, TelegramUser } from '../../api/types'

const POLL_MS = 1500

declare global {
  interface Window {
    onTelegramAuth?: (user: Record<string, unknown>) => void
  }
}

export function TelegramIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden fill="currentColor">
      <path d="M9.78 15.27 9.6 19.3c.37 0 .53-.16.73-.35l1.75-1.67 3.62 2.65c.66.37 1.13.18 1.31-.61l2.37-11.13c.24-1.03-.38-1.43-1.02-1.19L3.9 12.33c-.95.37-.94.9-.17 1.14l3.56 1.11 8.26-5.21c.39-.26.74-.11.45.15l-6.22 5.75Z" />
    </svg>
  )
}

/** Refetch everything after logging in or out: the server answers with or without private data. */
function useRefreshAll() {
  const queryClient = useQueryClient()
  return useCallback(() => void queryClient.invalidateQueries(), [queryClient])
}

export function LoginButton({ className, size = 'md' }: { className?: string; size?: 'sm' | 'md' }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={clsx(
          'inline-flex items-center justify-center gap-2 rounded-xl bg-[#229ED9] font-medium text-white shadow-sm transition-colors hover:bg-[#1b8cc2]',
          size === 'sm' ? 'h-8 px-3 text-xs' : 'h-9 px-4 text-[13px]',
          className,
        )}
      >
        <TelegramIcon className="size-4" />
        Log in with Telegram
      </button>
      {/* A portal: the frosted-glass sidebar would otherwise trap the fixed-position dialog. */}
      {open && createPortal(<LoginDialog onClose={() => setOpen(false)} />, document.body)}
    </>
  )
}

type Step = 'starting' | 'waiting' | 'expired' | 'forbidden' | 'error'

export function LoginDialog({ onClose }: { onClose: () => void }) {
  const auth = useAuth()
  const refreshAll = useRefreshAll()
  const [link, setLink] = useState<LoginLink | null>(null)
  const [step, setStep] = useState<Step>('starting')
  const [message, setMessage] = useState<string | null>(null)
  const showWidget = Boolean(auth.data?.widget_domain && auth.data.widget_domain === window.location.hostname)

  const start = useCallback(() => {
    setStep('starting')
    setMessage(null)
    api.auth
      .link()
      .then((created) => {
        setLink(created)
        setStep('waiting')
      })
      .catch((error: Error) => {
        setStep('error')
        setMessage(error.message)
      })
  }, [])

  useEffect(() => {
    if (auth.data?.enabled) start()
  }, [auth.data?.enabled, start])

  // Wait for the bot to see /start <code>, then the server sets the session cookie.
  useEffect(() => {
    if (step !== 'waiting' || !link) return
    const timer = window.setInterval(() => {
      api.auth
        .linkStatus(link.token)
        .then((result) => {
          if (result.status === 'done') {
            window.clearInterval(timer)
            refreshAll()
            onClose()
          } else if (result.status === 'forbidden') {
            setStep('forbidden')
          } else if (result.status !== 'pending') {
            setStep('expired')
          }
        })
        .catch(() => undefined)
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [step, link, refreshAll, onClose])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const onWidgetAuth = useCallback(
    (user: Record<string, unknown>) => {
      api.auth
        .widget(user)
        .then(() => {
          refreshAll()
          onClose()
        })
        .catch((error: Error) => {
          setStep('error')
          setMessage(error.message)
        })
    },
    [refreshAll, onClose],
  )

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal aria-label="Log in with Telegram">
      <div className="absolute inset-0 bg-slate-900/25 backdrop-blur-[2px]" onClick={onClose} />
      <div className="glass-strong relative w-full max-w-md animate-toast-in rounded-2xl p-6">
        <button type="button" onClick={onClose} aria-label="Close" className="absolute top-4 right-4 rounded-lg p-1 text-slate-400 hover:text-slate-900">
          <X className="size-4" aria-hidden />
        </button>
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-full bg-[#229ED9] text-white">
            <TelegramIcon className="size-5" />
          </span>
          <div>
            <h2 className="text-[17px] font-semibold text-slate-900">Log in with Telegram</h2>
            <p className="text-[13px] text-slate-500">The Telegram groups behind the ads are only shown after login.</p>
          </div>
        </div>

        {!auth.data?.enabled ? (
          <p className="mt-5 rounded-xl bg-amber-400/15 px-4 py-3 text-[13px] leading-5 text-amber-900">
            Login is not set up on this server yet. Add <code>TELEGRAM_BOT_TOKEN</code> and <code>TELEGRAM_BOT_USERNAME</code> to <code>.env</code>{' '}
            and restart it.
          </p>
        ) : (
          <div className="mt-5 space-y-4">
            {showWidget && auth.data.bot_username && (
              <div className="flex flex-col items-center gap-2 border-b border-slate-900/[0.06] pb-4">
                <TelegramWidget bot={auth.data.bot_username} onAuth={onWidgetAuth} />
                <span className="text-xs text-slate-500">or use the bot:</span>
              </div>
            )}
            <ol className="space-y-1.5 text-[13px] leading-5 text-slate-700">
              <li>
                1. Open <b>@{auth.data.bot_username}</b> in Telegram.
              </li>
              <li>
                2. Press <b>Start</b>. The bot confirms the login and this page unlocks by itself.
              </li>
            </ol>
            {link ? (
              <a
                href={link.url}
                target="_blank"
                rel="noreferrer"
                className="flex h-10 w-full items-center justify-center gap-2 rounded-xl bg-[#229ED9] text-[14px] font-medium text-white shadow-sm hover:bg-[#1b8cc2]"
              >
                <TelegramIcon className="size-4" />
                Open Telegram
                <ExternalLink className="size-3.5 opacity-80" aria-hidden />
              </a>
            ) : (
              <div className="flex h-10 items-center justify-center text-[13px] text-slate-500">
                <LoaderCircle className="mr-2 size-4 animate-spin" aria-hidden /> Preparing a login link…
              </div>
            )}
            <StepNote step={step} message={message} onRetry={start} />
          </div>
        )}
      </div>
    </div>
  )
}

function StepNote({ step, message, onRetry }: { step: Step; message: string | null; onRetry: () => void }) {
  if (step === 'waiting') {
    return (
      <p className="flex items-center justify-center gap-2 text-xs text-slate-500">
        <LoaderCircle className="size-3.5 animate-spin" aria-hidden /> Waiting for you to press Start in Telegram…
      </p>
    )
  }
  const text: Partial<Record<Step, string>> = {
    expired: 'This login link expired.',
    forbidden: 'This Telegram account is not allowed to see the Telegram groups.',
    error: message ?? 'Something went wrong.',
  }
  if (!text[step]) return null
  return (
    <p className="text-center text-xs text-rose-700">
      {text[step]}{' '}
      {step !== 'forbidden' && (
        <button type="button" onClick={onRetry} className="font-medium text-blue-700 underline">
          Try again
        </button>
      )}
    </p>
  )
}

/** The official Telegram Login Widget (works only on the domain set for the bot with /setdomain). */
function TelegramWidget({ bot, onAuth }: { bot: string; onAuth: (user: Record<string, unknown>) => void }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const host = ref.current
    if (!host) return
    window.onTelegramAuth = onAuth
    const script = document.createElement('script')
    script.src = 'https://telegram.org/js/telegram-widget.js?22'
    script.async = true
    script.setAttribute('data-telegram-login', bot)
    script.setAttribute('data-size', 'large')
    script.setAttribute('data-radius', '12')
    script.setAttribute('data-onauth', 'onTelegramAuth(user)')
    host.appendChild(script)
    return () => {
      host.innerHTML = ''
      delete window.onTelegramAuth
    }
  }, [bot, onAuth])
  return <div ref={ref} />
}

function displayName(user: TelegramUser): string {
  return [user.first_name, user.last_name].filter(Boolean).join(' ') || (user.username ? `@${user.username}` : `#${user.id}`)
}

function Avatar({ user }: { user: TelegramUser }) {
  const [broken, setBroken] = useState(false)
  if (user.photo_url && !broken) {
    return <img src={user.photo_url} alt="" className="size-8 shrink-0 rounded-full object-cover" onError={() => setBroken(true)} />
  }
  const initials = displayName(user)
    .replace('@', '')
    .split(' ')
    .map((part) => part[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
  return <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-[#229ED9] text-xs font-semibold text-white">{initials}</span>
}

/** Sidebar: the logged-in Telegram account with "Log out", or the login button. */
export function AccountBox() {
  const auth = useAuth()
  const refreshAll = useRefreshAll()
  if (!auth.data || (!auth.data.required && !auth.data.user)) return null
  const user = auth.data.user
  if (!user) {
    return (
      <div className="space-y-1.5">
        <LoginButton className="w-full" size="sm" />
        <p className="text-center text-[11px] leading-4 text-slate-500">to see the Telegram groups</p>
      </div>
    )
  }
  return (
    <div className="flex items-center gap-2.5 rounded-xl bg-white/50 px-2.5 py-2 ring-1 ring-slate-900/[0.05]">
      <Avatar user={user} />
      <div className="min-w-0 flex-1 leading-4">
        <div className="truncate text-[13px] font-medium text-slate-800">{displayName(user)}</div>
        <div className="truncate text-[11px] text-slate-500">
          {auth.data.allowed ? (user.username ? `@${user.username}` : 'Telegram') : 'not allowed to see private data'}
        </div>
      </div>
      <button
        type="button"
        title="Log out"
        aria-label="Log out"
        onClick={() => void api.auth.logout().then(refreshAll)}
        className="rounded-lg p-1.5 text-slate-400 hover:bg-white/70 hover:text-slate-900"
      >
        <LogOut className="size-4" aria-hidden />
      </button>
    </div>
  )
}

/** Shown instead of province or Telegram group data until the visitor logs in. */
export function LockedCard({ title, children, compact = false, className }: { title: string; children?: ReactNode; compact?: boolean; className?: string }) {
  return (
    <section className={clsx('glass flex flex-col items-center text-center', compact ? 'px-5 py-8' : 'px-8 py-16', className)}>
      <span className="flex size-10 items-center justify-center rounded-full bg-slate-900/[0.05] text-slate-500">
        <Lock className="size-5" aria-hidden />
      </span>
      <h2 className="mt-3 text-[15px] font-semibold text-slate-900">{title}</h2>
      <p className="mt-1 max-w-sm text-[13px] leading-5 text-slate-500">
        {children ?? 'Telegram group details are only shown after you log in with Telegram.'}
      </p>
      <LoginButton className="mt-4" />
    </section>
  )
}
