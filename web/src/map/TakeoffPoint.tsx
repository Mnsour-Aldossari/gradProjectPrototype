import L from 'leaflet'
import { useEffect } from 'react'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { LatLon } from '../types'

// Made once each: a new icon on every render would make Leaflet rebuild the marker and stop a drag.
const ICONS = {
  H: L.divIcon({ className: 'takeoff-icon', html: '<span aria-hidden="true">H</span>', iconSize: [30, 30], iconAnchor: [15, 15] }),
  L: L.divIcon({
    className: 'takeoff-icon landing-icon',
    html: '<span aria-hidden="true">L</span>',
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  }),
}

/** Whether a point lies inside a lat/lon outline (ray casting; fine over a few hundred metres). */
export function insideArea(p: LatLon, area: LatLon[]): boolean {
  let inside = false
  for (let i = 0, j = area.length - 1; i < area.length; j = i++) {
    const [yi, xi] = area[i]
    const [yj, xj] = area[j]
    if (yi > p[0] !== yj > p[0] && p[1] < xi + ((p[0] - yi) * (xj - xi)) / (yj - yi)) inside = !inside
  }
  return inside
}

/** Ground distance in metres between two nearby points (equirectangular, like the backend's LocalFrame). */
export function distanceM(a: LatLon, b: LatLon): number {
  const r = 6_371_008.8
  const rad = Math.PI / 180
  const x = (b[1] - a[1]) * rad * r * Math.cos(((a[0] + b[0]) / 2) * rad)
  const y = (b[0] - a[0]) * rad * r
  return Math.hypot(x, y)
}

/**
 * PX4's takeoff point (an H pad) or landing point (L) on the map. While picking, a click on the map sets it; it can
 * also be dragged. Goes inside SurveyMap.
 */
export function TakeoffPoint({
  point,
  letter = 'H',
  picking = false,
  editable = false,
  onPick,
}: {
  point: LatLon
  letter?: 'H' | 'L'
  picking?: boolean
  editable?: boolean
  onPick?: (p: LatLon) => void
}) {
  const map = useMap()
  useMapEvents({
    click(e) {
      if (picking) onPick?.([e.latlng.lat, e.latlng.lng])
    },
  })
  useEffect(() => {
    const el = map.getContainer()
    el.classList.toggle('picking-takeoff', picking)
    return () => el.classList.remove('picking-takeoff')
  }, [map, picking])

  return (
    <Marker
      position={point}
      icon={ICONS[letter]}
      draggable={editable}
      keyboard={false}
      title={letter === 'H' ? 'Takeoff point' : 'Landing point'}
      zIndexOffset={900}
      eventHandlers={{
        dragend: (e) => {
          const p = (e.target as L.Marker).getLatLng()
          onPick?.([p.lat, p.lng])
        },
      }}
    />
  )
}
