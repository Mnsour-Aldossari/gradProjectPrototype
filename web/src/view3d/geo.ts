import type { LatLon } from '../types'

/**
 * Local flat-earth frame in metres around the survey area's centre, the same as LocalFrame in
 * backend/app/simulation/geo.py, so the scene lines up with the backend's survey path and detections.
 * x = east, y = north. In the scene, east is +X, north is -Z and height is +Y.
 */
const EARTH_RADIUS_M = 6_371_008.8
const rad = (deg: number) => (deg * Math.PI) / 180

export interface Frame {
  lat0: number
  lon0: number
}

export function centredOn(area: LatLon[]): Frame {
  return {
    lat0: area.reduce((s, p) => s + p[0], 0) / area.length,
    lon0: area.reduce((s, p) => s + p[1], 0) / area.length,
  }
}

export function toXY(f: Frame, lat: number, lon: number): [number, number] {
  return [rad(lon - f.lon0) * EARTH_RADIUS_M * Math.cos(rad(f.lat0)), rad(lat - f.lat0) * EARTH_RADIUS_M]
}

/** Web Mercator tile coordinates (fractional) of a point, as used by the map's satellite tiles. */
export function tileXY(lat: number, lon: number, z: number): [number, number] {
  const n = 2 ** z
  const x = ((lon + 180) / 360) * n
  const y = ((1 - Math.log(Math.tan(rad(lat)) + 1 / Math.cos(rad(lat))) / Math.PI) / 2) * n
  return [x, y]
}

/** Latitude and longitude of a tile corner. */
export function tileLatLon(x: number, y: number, z: number): LatLon {
  const n = 2 ** z
  const lon = (x / n) * 360 - 180
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / n))) * 180) / Math.PI
  return [lat, lon]
}
