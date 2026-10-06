// Live layer: one EventSource('/api/events') for the app, backoff reconnects, /api/health polling fallback,
// stats invalidation on updates, province pulses and toasts. Read it anywhere with useLive().
import { useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { EVENTS_URL, api, isOfflineError } from '../api/client'
import { useHealth } from '../api/hooks'
import { invalidateStats, queryKeys } from '../api/queryClient'
import type { Health, HelloEvent, UpdateEvent } from '../api/types'
import { fmtInt, parseApiDate, plural } from '../lib/format'

export type LiveStatus = 'connecting' | 'live' | 'reconnecting' | 'loading' | 'offline'
export type ToastTone = 'info' | 'success' | 'warning'

export interface Toast {
  id: number
  title: string
  body?: string
  tone: ToastTone
}

export interface LiveContextValue {
  /** connecting → live; reconnecting while SSE retries; loading while the store builds; offline when unreachable. */
  status: LiveStatus
  /** 'sse' while the stream is open, 'polling' while falling back to /api/health polling. */
  transport: 'sse' | 'polling'
  /** Store loading progress 0..1 (null when not loading). */
  progress: number | null
  /** Latest store version seen (null before the first contact). */
  version: number | null
  /** Epoch ms of the last ingest that added posts (from SSE or health.last_update). */
  lastUpdateAt: number | null
  /** Most recent `update` event. */
  lastEvent: UpdateEvent | null
  /** Province id → epoch ms its pulse started; entries are dropped after PULSE_MS. */
  pulses: Record<string, number>
  toasts: Toast[]
  pushToast: (t: Omit<Toast, 'id'>) => void
  dismissToast: (id: number) => void
}

/** How long a province pulses after new ads arrive. */
export const PULSE_MS = 3000
const TOAST_MS = 4500
const POLL_MS = 10_000
const POLL_OFFLINE_MS = 5_000
const MAX_BACKOFF_MS = 30_000

const LiveContext = createContext<LiveContextValue | null>(null)

type Conn = 'connecting' | 'open' | 'retrying'

function parse<T>(e: MessageEvent): T | null {
  try {
    return JSON.parse(e.data as string) as T
  } catch {
    return null
  }
}

/** Provides live status, pulses and toasts; must sit inside QueryClientProvider. */
export function LiveProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const health = useHealth()

  const [conn, setConn] = useState<Conn>('connecting')
  const [lastEvent, setLastEvent] = useState<UpdateEvent | null>(null)
  const [eventAt, setEventAt] = useState<number | null>(null)
  const [pulses, setPulses] = useState<Record<string, number>>({})
  const [toasts, setToasts] = useState<Toast[]>([])

  const versionRef = useRef<number | null>(null)
  const toastSeq = useRef(0)
  const toastTimers = useRef(new Map<number, number>())
  // Consecutive live-update toasts are merged into one while it is visible.
  const updateToast = useRef<{ id: number; posts: number; ads: number } | null>(null)

  const dismissToast = useCallback((id: number) => {
    setToasts((ts) => ts.filter((t) => t.id !== id))
    const timer = toastTimers.current.get(id)
    if (timer) window.clearTimeout(timer)
    toastTimers.current.delete(id)
    if (updateToast.current?.id === id) updateToast.current = null
  }, [])

  const scheduleDismiss = useCallback(
    (id: number) => {
      const old = toastTimers.current.get(id)
      if (old) window.clearTimeout(old)
      toastTimers.current.set(
        id,
        window.setTimeout(() => dismissToast(id), TOAST_MS),
      )
    },
    [dismissToast],
  )

  const pushToast = useCallback(
    (t: Omit<Toast, 'id'>) => {
      const id = ++toastSeq.current
      setToasts((ts) => [...ts.slice(-2), { ...t, id }])
      scheduleDismiss(id)
      return id
    },
    [scheduleDismiss],
  )

  /** Records a new store version; refetches stats when it changed. */
  const seeVersion = useCallback(
    (v: number, force = false) => {
      const prev = versionRef.current
      versionRef.current = v
      if (force || (prev !== null && prev !== v)) void invalidateStats(queryClient)
    },
    [queryClient],
  )

  const onUpdate = useCallback(
    (u: UpdateEvent) => {
      seeVersion(u.version, true)
      setLastEvent(u)
      setEventAt(parseApiDate(u.at)?.getTime() ?? Date.now())
      queryClient.setQueryData<Health>(queryKeys.health, (old) =>
        old ? { ...old, version: u.version, posts: u.posts, unique_ads: u.unique_ads, last_update: u.at } : old,
      )

      const now = Date.now()
      const hit = Object.entries(u.provinces ?? {}).filter(([, n]) => n > 0)
      if (hit.length) setPulses((p) => ({ ...p, ...Object.fromEntries(hit.map(([k]) => [k, now])) }))

      if (u.added_posts > 0) {
        const cur = updateToast.current
        const posts = (cur?.posts ?? 0) + u.added_posts
        const ads = (cur?.ads ?? 0) + u.added_ads
        const title = `+${fmtInt(posts)} new ${posts === 1 ? 'post' : 'posts'}`
        const body = ads > 0 ? `${plural(ads, 'new unique ad')}` : 'Reposts of ads already counted'
        if (cur) {
          updateToast.current = { id: cur.id, posts, ads }
          setToasts((ts) => ts.map((t) => (t.id === cur.id ? { ...t, title, body } : t)))
          scheduleDismiss(cur.id)
        } else {
          const id = pushToast({ title, body, tone: 'info' })
          updateToast.current = { id, posts, ads }
        }
      }
    },
    [pushToast, queryClient, scheduleDismiss, seeVersion],
  )

  // Drop pulses after PULSE_MS.
  useEffect(() => {
    const ids = Object.keys(pulses)
    if (!ids.length) return
    const oldest = Math.min(...Object.values(pulses))
    const t = window.setTimeout(
      () => {
        const cutoff = Date.now() - PULSE_MS
        setPulses((p) => Object.fromEntries(Object.entries(p).filter(([, at]) => at > cutoff)))
      },
      Math.max(50, oldest + PULSE_MS - Date.now()),
    )
    return () => window.clearTimeout(t)
  }, [pulses])

  // The EventSource with exponential backoff, plus /api/health polling while it is down.
  useEffect(() => {
    let es: EventSource | null = null
    let attempt = 0
    let everOpened = false
    let reconnectTimer: number | undefined
    let pollTimer: number | undefined
    let disposed = false

    const pollHealth = async () => {
      pollTimer = undefined
      let reachable = false
      try {
        const h = await queryClient.fetchQuery({
          queryKey: queryKeys.health,
          queryFn: ({ signal }) => api.health(signal),
          staleTime: 0,
          retry: false,
        })
        reachable = true
        seeVersion(h.version)
        // Backend is back: retry the stream now instead of waiting out a long backoff.
        if (!es && reconnectTimer !== undefined && attempt > 1) {
          window.clearTimeout(reconnectTimer)
          reconnectTimer = undefined
          attempt = 0
          connect()
        }
      } catch {
        // The health query now holds the error; status derives 'offline' from it.
      }
      if (!disposed && !es) pollTimer = window.setTimeout(pollHealth, reachable ? POLL_MS : POLL_OFFLINE_MS)
    }

    const startPolling = () => {
      if (pollTimer === undefined) pollTimer = window.setTimeout(pollHealth, attempt <= 1 ? 1000 : POLL_MS)
    }
    const stopPolling = () => {
      if (pollTimer !== undefined) window.clearTimeout(pollTimer)
      pollTimer = undefined
    }

    const connect = () => {
      if (disposed) return
      const source = new EventSource(EVENTS_URL)
      es = source

      source.onopen = () => {
        const wasDown = attempt > 0 || everOpened
        attempt = 0
        everOpened = true
        stopPolling()
        setConn('open')
        // Anything may have changed while we were away.
        if (wasDown) {
          void queryClient.invalidateQueries({ queryKey: queryKeys.health })
          void invalidateStats(queryClient)
        }
      }
      source.addEventListener('hello', (e) => {
        const h = parse<HelloEvent>(e as MessageEvent)
        if (!h) return
        seeVersion(h.version)
        queryClient.setQueryData<Health>(queryKeys.health, (old) =>
          old ? { ...old, version: h.version, status: h.status, progress: h.status === 'loading' ? old.progress : 1 } : old,
        )
        if (h.status === 'loading') void queryClient.invalidateQueries({ queryKey: queryKeys.health })
      })
      source.addEventListener('status', (e) => {
        const h = parse<Health>(e as MessageEvent)
        if (!h) return
        const prev = queryClient.getQueryData<Health>(queryKeys.health)
        queryClient.setQueryData<Health>(queryKeys.health, h)
        seeVersion(h.version, prev?.status === 'loading' && h.status === 'ready')
      })
      source.addEventListener('update', (e) => {
        const u = parse<UpdateEvent>(e as MessageEvent)
        if (u) onUpdate(u)
      })
      source.onerror = () => {
        // Close and retry ourselves: the browser gives up for good on non-200 answers (e.g. proxy 502).
        source.close()
        if (es === source) es = null
        if (disposed) return
        setConn(everOpened || attempt > 0 ? 'retrying' : 'connecting')
        const delay = Math.min(MAX_BACKOFF_MS, 1000 * 2 ** attempt) * (0.8 + Math.random() * 0.4)
        attempt += 1
        if (attempt >= 2) setConn('retrying')
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = undefined
          connect()
        }, delay)
        startPolling()
      }
    }

    connect()
    return () => {
      disposed = true
      es?.close()
      if (reconnectTimer !== undefined) window.clearTimeout(reconnectTimer)
      stopPolling()
    }
  }, [onUpdate, queryClient, seeVersion])

  // Clear toast timers on unmount.
  useEffect(() => {
    const timers = toastTimers.current
    return () => timers.forEach((t) => window.clearTimeout(t))
  }, [])

  const h = health.data
  const failing = health.isError && isOfflineError(health.error) && health.errorUpdatedAt >= health.dataUpdatedAt
  const status: LiveStatus =
    failing && conn !== 'open'
      ? 'offline'
      : h?.status === 'loading'
        ? 'loading'
        : conn === 'open'
          ? 'live'
          : conn === 'connecting'
            ? 'connecting'
            : 'reconnecting'

  const healthAt = parseApiDate(h?.last_update)?.getTime() ?? null
  const lastUpdateAt = eventAt !== null && (healthAt === null || eventAt > healthAt) ? eventAt : healthAt

  const value = useMemo<LiveContextValue>(
    () => ({
      status,
      transport: conn === 'open' ? 'sse' : 'polling',
      progress: h?.status === 'loading' ? h.progress : null,
      version: h?.version ?? versionRef.current,
      lastUpdateAt,
      lastEvent,
      pulses,
      toasts,
      pushToast: (t) => void pushToast(t),
      dismissToast,
    }),
    [status, conn, h?.status, h?.progress, h?.version, lastUpdateAt, lastEvent, pulses, toasts, pushToast, dismissToast],
  )

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>
}

/** Live status, version, pulses and toasts (throws outside LiveProvider). */
export function useLive(): LiveContextValue {
  const ctx = useContext(LiveContext)
  if (!ctx) throw new Error('useLive must be used inside <LiveProvider>')
  return ctx
}

/** True while `province` is pulsing after an update (re-renders with useLive). */
export function useIsPulsing(province: string | null | undefined): boolean {
  const { pulses } = useLive()
  return province ? province in pulses : false
}
