import L from 'leaflet'
import { useEffect } from 'react'
import { Marker, useMap, useMapEvents } from 'react-leaflet'
import type { LatLon } from '../types'

const ICON = L.divIcon({
  className: 'takeoff-icon',
  html: '<span aria-hidden="true">H</span>',
  iconSize: [30, 30],
  iconAnchor: [15, 15],
})

/** Ground distance in metres between two nearby points (equirectangular, like the backend's LocalFrame). */
export function distanceM(a: LatLon, b: LatLon): number {
  const r = 6_371_008.8
  const rad = Math.PI / 180
  const x = (b[1] - a[1]) * rad * r * Math.cos(((a[0] + b[0]) / 2) * rad)
  const y = (b[0] - a[0]) * rad * r
  return Math.hypot(x, y)
}

/**
 * PX4's takeoff point on the map (an H pad). While picking, a click on the map sets it; it can also be dragged.
 * Goes inside SurveyMap.
 */
export function TakeoffPoint({
  point,
  picking = false,
  editable = false,
  onPick,
}: {
  point: LatLon
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
      icon={ICON}
      draggable={editable}
      keyboard={false}
      title="Takeoff point"
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
