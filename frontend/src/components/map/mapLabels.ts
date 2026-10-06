// Hand-tuned label positions [lon, lat]. Metros get their label inside when it fits, otherwise at `outside`
// with a thin leader line from `origin` (open sea or a quiet part of a neighbouring province).
import type { ProvinceId } from '../../api/types'

export interface LabelSpot {
  at: [number, number]
  outside?: [number, number]
  origin?: [number, number]
}

export const LABEL_SPOTS: Record<ProvinceId, LabelSpot> = {
  'Gyeonggi-do': { at: [127.4, 37.2] },
  'Gangwon-do': { at: [128.3, 37.75] },
  'Chungcheongbuk-do': { at: [127.88, 36.86] },
  'Chungcheongnam-do': { at: [126.78, 36.45] },
  'Jeollabuk-do': { at: [127.15, 35.72] },
  'Jeollanam-do': { at: [126.95, 34.86] },
  'Gyeongsangbuk-do': { at: [128.78, 36.45] },
  'Gyeongsangnam-do': { at: [128.22, 35.33] },
  'Jeju-do': { at: [126.56, 33.37] },
  Seoul: { at: [126.99, 37.56], outside: [126.5, 38.12] },
  Incheon: { at: [126.68, 37.46], outside: [125.9, 37.28], origin: [126.68, 37.46] },
  Sejong: { at: [127.26, 36.57], outside: [126.98, 36.92] },
  Daejeon: { at: [127.4, 36.34], outside: [127.74, 36.2] },
  Gwangju: { at: [126.84, 35.15], outside: [126.42, 35.33] },
  Daegu: { at: [128.57, 35.83], outside: [129.0, 35.98] },
  Ulsan: { at: [129.24, 35.55], outside: [129.78, 35.62] },
  Busan: { at: [129.06, 35.2], outside: [129.6, 34.88] },
}

/** Polygons left out when fitting the projection (Baengnyeongdo, Ulleungdo) so the mainland stays large. */
export const FIT_LON_RANGE: [number, number] = [124.95, 130.3]
