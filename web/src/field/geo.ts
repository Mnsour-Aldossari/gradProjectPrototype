import type { LatLon } from '../types'

const R = 6_371_008.8

export function distanceM(a: LatLon, b: LatLon): number {
  const [lat1, lon1] = a.map((v) => (v * Math.PI) / 180)
  const [lat2, lon2] = b.map((v) => (v * Math.PI) / 180)
  const h = Math.sin((lat2 - lat1) / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin((lon2 - lon1) / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

const DIRECTIONS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']

export function bearing(a: LatLon, b: LatLon): string {
  const [lat1, lon1] = a.map((v) => (v * Math.PI) / 180)
  const [lat2, lon2] = b.map((v) => (v * Math.PI) / 180)
  const y = Math.sin(lon2 - lon1) * Math.cos(lat2)
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lon2 - lon1)
  const deg = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
  return DIRECTIONS[Math.round(deg / 45) % 8]
}

export function formatDistance(m: number): string {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`
}

export function centre(area: LatLon[]): LatLon {
  return [area.reduce((s, p) => s + p[0], 0) / area.length, area.reduce((s, p) => s + p[1], 0) / area.length]
}
