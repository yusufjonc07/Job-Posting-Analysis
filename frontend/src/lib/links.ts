// Links that keep the current filters (?days, ?source, ?basis) when moving between pages.
import { useCallback } from 'react'
import { useSearchParams } from 'react-router'

const FILTER_KEYS = ['days', 'source', 'basis'] as const

/** linkTo('/map', { region: 'Seoul' }) → '/map?days=30&region=Seoul' (current filters kept). */
export function useLinkTo(): (path: string, extra?: Record<string, string>) => string {
  const [sp] = useSearchParams()
  return useCallback(
    (path: string, extra: Record<string, string> = {}) => {
      const next = new URLSearchParams()
      for (const key of FILTER_KEYS) {
        const value = sp.get(key)
        if (value !== null) next.set(key, value)
      }
      for (const [key, value] of Object.entries(extra)) next.set(key, value)
      const q = next.toString()
      return q ? `${path}?${q}` : path
    },
    [sp],
  )
}
