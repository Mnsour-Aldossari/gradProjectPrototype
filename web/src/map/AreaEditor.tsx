import L from 'leaflet'
import { useEffect, useState } from 'react'
import { CircleMarker, Marker, Polygon, Polyline, useMap, useMapEvents } from 'react-leaflet'
import { COLORS } from '../theme'
import type { LatLon } from '../types'

export type DrawTool = 'rect' | 'circle' | 'polygon'

/** How an outline was drawn, so it can be edited the same way: a circle by its centre and radius, else its corners. */
export type Shape = { kind: 'circle'; centre: LatLon; radiusM: number } | { kind: 'polygon'; points: LatLon[] }

const M_PER_DEG_LAT = 111_195
const CIRCLE_POINTS = 32
const CLOSE_PX = 14 // a click this near the first corner closes a free shape

const mPerDegLon = (lat: number) => M_PER_DEG_LAT * Math.cos((lat * Math.PI) / 180)

export function distanceM(a: LatLon, b: LatLon): number {
  return Math.hypot((b[0] - a[0]) * M_PER_DEG_LAT, (b[1] - a[1]) * mPerDegLon((a[0] + b[0]) / 2))
}

export function rectangle(a: LatLon, b: LatLon): LatLon[] {
  const [n, s] = [Math.max(a[0], b[0]), Math.min(a[0], b[0])]
  const [e, w] = [Math.max(a[1], b[1]), Math.min(a[1], b[1])]
  return [
    [n, w],
    [n, e],
    [s, e],
    [s, w],
  ]
}

export function circle(centre: LatLon, radiusM: number): LatLon[] {
  return Array.from({ length: CIRCLE_POINTS }, (_, i) => {
    const a = (2 * Math.PI * i) / CIRCLE_POINTS
    return [centre[0] + (radiusM * Math.sin(a)) / M_PER_DEG_LAT, centre[1] + (radiusM * Math.cos(a)) / mPerDegLon(centre[0])]
  })
}

export function outline(shape: Shape): LatLon[] {
  return shape.kind === 'circle' ? circle(shape.centre, shape.radiusM) : shape.points
}

// Made once: a new icon on every render would make Leaflet rebuild the handle, and stop a drag under way.
const HANDLE_ICONS = Object.fromEntries(
  (['corner', 'centre', 'radius'] as const).map((kind) => [
    kind,
    L.divIcon({ className: `area-handle area-handle-${kind}`, iconSize: [16, 16], iconAnchor: [8, 8] }),
  ]),
) as Record<'corner' | 'centre' | 'radius', L.DivIcon>
const handleIcon = (kind: 'corner' | 'centre' | 'radius') => HANDLE_ICONS[kind]

const latLon = (e: L.LeafletMouseEvent | L.LeafletEvent): LatLon => {
  const p = 'latlng' in e ? (e as L.LeafletMouseEvent).latlng : (e.target as L.Marker).getLatLng()
  return [p.lat, p.lng]
}

/**
 * Drawing a survey outline on the map. Rectangle: two opposite corners. Circle: the centre, then a point on the edge.
 * Free shape: a click per corner; a click on the first corner (or a double-click) closes it; Backspace removes the
 * last corner, Escape cancels. `onDraft` gets the outline so far (with the pointer as its next corner), for live
 * checking; `onDone` the finished shape.
 */
export function AreaDrawer({
  tool,
  color,
  onDraft,
  onDone,
  onCancel,
}: {
  tool: DrawTool
  color: string
  onDraft: (area: LatLon[] | null, corners: number) => void
  onDone: (shape: Shape) => void
  onCancel: () => void
}) {
  const map = useMap()
  const [points, setPoints] = useState<LatLon[]>([])
  const [hover, setHover] = useState<LatLon | null>(null)

  useEffect(() => {
    map.doubleClickZoom.disable()
    const el = map.getContainer()
    el.classList.add('drawing-area')
    return () => {
      map.doubleClickZoom.enable()
      el.classList.remove('drawing-area')
    }
  }, [map])

  useEffect(() => setPoints([]), [tool])

  const draft: LatLon[] | null = (() => {
    if (!points.length) return null
    const to = hover ?? points[points.length - 1]
    if (tool === 'rect') return rectangle(points[0], to)
    if (tool === 'circle') return circle(points[0], Math.max(0.5, distanceM(points[0], to)))
    return hover ? [...points, hover] : points
  })()

  const draftKey = JSON.stringify(draft)
  useEffect(() => {
    onDraft(draft && draft.length >= 3 ? draft : null, points.length)
  }, [draftKey, points.length])

  function finishFree(corners: LatLon[]) {
    if (corners.length >= 3) onDone({ kind: 'polygon', points: corners })
    setPoints([])
  }

  useMapEvents({
    click(e) {
      const p = latLon(e)
      if (tool === 'polygon') {
        if (points.length >= 3) {
          const a = map.latLngToContainerPoint(points[0])
          if (a.distanceTo(e.containerPoint) <= CLOSE_PX) return finishFree(points)
        }
        setPoints((ps) => [...ps, p])
      } else if (!points.length) {
        setPoints([p])
      } else {
        onDone(
          tool === 'rect'
            ? { kind: 'polygon', points: rectangle(points[0], p) }
            : { kind: 'circle', centre: points[0], radiusM: Math.max(0.5, distanceM(points[0], p)) },
        )
        setPoints([])
      }
    },
    dblclick() {
      // The double-click's own two clicks added the last corner twice: drop the repeat.
      if (tool === 'polygon') finishFree(points.slice(0, -1))
    },
    mousemove(e) {
      setHover(latLon(e))
    },
    keydown(e) {
      const key = (e.originalEvent as KeyboardEvent).key
      if (key === 'Escape') onCancel()
      if (key === 'Backspace' && tool === 'polygon') setPoints((ps) => ps.slice(0, -1))
    },
  })

  if (!draft) return null
  const style = { color, weight: 2, dashArray: '6 6', fillColor: color, fillOpacity: 0.12 }
  return (
    <>
      {tool === 'polygon' && !hover ? (
        <Polyline positions={draft} interactive={false} pathOptions={style} />
      ) : (
        <Polygon positions={draft} interactive={false} pathOptions={style} />
      )}
      {tool === 'polygon' &&
        points.map((p, i) => (
          <CircleMarker
            key={i}
            center={p}
            radius={i === 0 && points.length >= 3 ? 7 : 4}
            interactive={false}
            pathOptions={{ color: '#fff', weight: 2, fillColor: color, fillOpacity: 1 }}
          />
        ))}
    </>
  )
}

/** Handles to change a drawn outline: drag a corner, or a circle's centre (moves it) and edge (resizes it). */
export function AreaHandles({ shape, onChange, onEnd }: { shape: Shape; onChange: (s: Shape) => void; onEnd: () => void }) {
  if (shape.kind === 'circle') {
    const edge: LatLon = [shape.centre[0], shape.centre[1] + shape.radiusM / mPerDegLon(shape.centre[0])]
    return (
      <>
        <Marker
          position={shape.centre}
          icon={handleIcon('centre')}
          draggable
          title="Move the circle"
          eventHandlers={{ drag: (e) => onChange({ ...shape, centre: latLon(e) }), dragend: onEnd }}
        />
        <Marker
          position={edge}
          icon={handleIcon('radius')}
          draggable
          title="Resize the circle"
          eventHandlers={{
            drag: (e) => onChange({ ...shape, radiusM: Math.max(0.5, distanceM(shape.centre, latLon(e))) }),
            dragend: onEnd,
          }}
        />
      </>
    )
  }
  return (
    <>
      {shape.points.map((p, i) => (
        <Marker
          key={i}
          position={p}
          icon={handleIcon('corner')}
          draggable
          title={`Corner ${i + 1}`}
          eventHandlers={{
            drag: (e) => onChange({ kind: 'polygon', points: shape.points.map((q, j) => (j === i ? latLon(e) : q)) }),
            dragend: onEnd,
          }}
        />
      ))}
    </>
  )
}

export const OUTLINE_COLORS = { ok: COLORS.survey, bad: COLORS.hazard, drawing: COLORS.amber }
