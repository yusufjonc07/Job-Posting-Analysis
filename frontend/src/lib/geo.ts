// Typed access to the province boundaries (KOSTAT 2013) used by the map: properties.id = backend province id.
import type { Feature, FeatureCollection, MultiPolygon, Polygon } from 'geojson'
import type { ProvinceId } from '../api/types'
import raw from '../assets/korea-provinces.geo.json'

export interface ProvinceProps {
  /** Backend province id, e.g. 'Seoul', 'Gyeonggi-do', 'Sejong'. */
  id: ProvinceId
  /** Official Korean name, e.g. '서울특별시'. */
  name: string
  /** English name from the boundary file ('Sejongsi' for Sejong). */
  name_eng: string
  /** KOSTAT province code. */
  code: string
}

export type ProvinceFeature = Feature<Polygon | MultiPolygon, ProvinceProps>

/** All 17 provinces in backend order. */
export const provinceGeo = raw as unknown as FeatureCollection<Polygon | MultiPolygon, ProvinceProps>

export { BOUNDARIES_CREDIT } from './constants'
