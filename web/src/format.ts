export function formatDuration(seconds: number): string {
  const s = Math.max(0, Math.round(seconds))
  const m = Math.floor(s / 60)
  return `${m}:${String(s % 60).padStart(2, '0')}`
}

export function formatDate(iso: string | null): string {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
}

export function formatCoord(value: number): string {
  return value.toFixed(6)
}

/** Size of the bounding box of a lat/lon polygon, in metres. */
export function areaSize(area: [number, number][]): { width: number; height: number } {
  const lats = area.map((p) => p[0])
  const lons = area.map((p) => p[1])
  const lat0 = (Math.min(...lats) + Math.max(...lats)) / 2
  const mPerDegLat = 111_195
  const mPerDegLon = mPerDegLat * Math.cos((lat0 * Math.PI) / 180)
  return {
    width: (Math.max(...lons) - Math.min(...lons)) * mPerDegLon,
    height: (Math.max(...lats) - Math.min(...lats)) * mPerDegLat,
  }
}
