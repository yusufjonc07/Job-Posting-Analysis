// Selected map region synced with ?region=<province id> in the URL.
import { useCallback } from 'react'
import { useSearchParams } from 'react-router'
import { PROVINCE_IDS, type ProvinceId } from '../api/types'

/** Type guard for the 17 backend province ids. */
export const isProvinceId = (v: unknown): v is ProvinceId =>
  typeof v === 'string' && (PROVINCE_IDS as readonly string[]).includes(v)

/** [region, setRegion]: region is null when nothing (or an unknown id) is selected; setRegion(null) clears it. */
export function useSelectedRegion(): [ProvinceId | null, (region: ProvinceId | null) => void] {
  const [sp, setSp] = useSearchParams()
  const raw = sp.get('region')
  const region = isProvinceId(raw) ? raw : null

  const setRegion = useCallback(
    (next: ProvinceId | null) =>
      setSp(
        (prev) => {
          const p = new URLSearchParams(prev)
          if (next) p.set('region', next)
          else p.delete('region')
          return p
        },
        { replace: true },
      ),
    [setSp],
  )
  return [region, setRegion]
}
