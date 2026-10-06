// Display labels shared across pages: provinces, pay periods, location sources.
import { PROVINCE_IDS, type LocationSource, type Period, type ProvinceId } from '../api/types'

/** Korean short names of the 17 provinces (spec §4). */
export const PROVINCE_NAME_KO: Record<ProvinceId, string> = {
  Seoul: '서울',
  Busan: '부산',
  Daegu: '대구',
  Incheon: '인천',
  Gwangju: '광주',
  Daejeon: '대전',
  Ulsan: '울산',
  Sejong: '세종',
  'Gyeonggi-do': '경기',
  'Gangwon-do': '강원',
  'Chungcheongbuk-do': '충북',
  'Chungcheongnam-do': '충남',
  'Jeollabuk-do': '전북',
  'Jeollanam-do': '전남',
  'Gyeongsangbuk-do': '경북',
  'Gyeongsangnam-do': '경남',
  'Jeju-do': '제주',
}

/** The 17 provinces with labels, in backend order. */
export const PROVINCES: { id: ProvinceId; name: string; name_ko: string }[] = PROVINCE_IDS.map((id) => ({
  id,
  name: id,
  name_ko: PROVINCE_NAME_KO[id],
}))

/** English display name of a province id ('Gyeonggi-do' stays as is); unknown ids pass through. */
export function provinceLabel(id: string | null | undefined): string {
  if (!id) return 'Unknown'
  if (id === 'Nationwide') return 'Nationwide'
  return id
}

export const PERIODS: Period[] = ['hourly', 'daily', 'monthly']
export const PERIOD_LABELS: Record<Period, string> = { hourly: 'Hourly', daily: 'Daily', monthly: 'Monthly' }

export const LOCATION_SOURCES: LocationSource[] = ['address', 'text', 'group', 'unknown']
export const SOURCE_LABELS: Record<LocationSource, string> = {
  address: 'Korean address',
  text: 'Place name in text',
  group: 'Group home location',
  unknown: 'No location',
}

/** Copy used wherever volume over time is shown. */
export const FORWARDED_NOTE =
  "Forwarded posts from the Ish e'lonlari bot only exist from Aug 2026 — the jump is a data-source change, not job growth."
