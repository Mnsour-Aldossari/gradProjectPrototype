import L from 'leaflet'
import { useEffect, useRef, useState } from 'react'
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

/** Area of an outline in m², on a local flat projection (fine at survey sizes). */
export function areaM2(points: LatLon[]): number {
  if (points.length < 3) return 0
  const lat0 = points[0][0]
  const xy = points.map(([lat, lon]) => [(lon - points[0][1]) * mPerDegLon(lat0), (lat - lat0) * M_PER_DEG_LAT])
  let sum = 0
  for (let i = 0; i < xy.length; i++) {
    const [x1, y1] = xy[i]
    const [x2, y2] = xy[(i + 1) % xy.length]
    sum += x1 * y2 - x2 * y1
  }
  return Math.abs(sum) / 2
}

export function centroid(points: LatLon[]): LatLon {
  return [points.reduce((s, p) => s + p[0], 0) / points.length, points.reduce((s, p) => s + p[1], 0) / points.length]
}

const midpoint = (a: LatLon, b: LatLon): LatLon => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]

export function formatLength(m: number): string {
  return m >= 1000 ? `${(m / 1000).toFixed(2)} km` : `${m < 10 ? m.toFixed(1) : m.toFixed(0)} m`
}

export function formatArea(m2: number): string {
  return m2 >= 10_000 ? `${(m2 / 10_000).toFixed(2)} ha` : `${m2.toFixed(0)} m²`
}

/** A text label placed on the map (measurements); it never takes clicks. */
function labelIcon(text: string, kind: string): L.DivIcon {
  return L.divIcon({ className: `map-measure map-measure-${kind}`, html: `<span>${text}</span>`, iconSize: [0, 0] })
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
const GHOST_ICON = L.divIcon({ className: 'area-handle area-handle-ghost', iconSize: [12, 12], iconAnchor: [6, 6] })
const MOVE_ICON = L.divIcon({
  className: 'area-handle area-handle-move',
  html: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/></svg>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
})

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
  const style = { color, weight: 2.5, dashArray: '6 6', fillColor: color, fillOpacity: 0.14 }
  // What the pointer would make: the size of the rectangle, the circle's radius, the free shape's next side.
  const live = (() => {
    if (!hover) return null
    if (tool === 'rect') {
      const r = rectangle(points[0], hover)
      return `${formatLength(distanceM(r[0], r[1]))} × ${formatLength(distanceM(r[1], r[2]))} · ${formatArea(areaM2(r))}`
    }
    if (tool === 'circle') {
      const radius = distanceM(points[0], hover)
      return `r ${formatLength(radius)} · ${formatArea(Math.PI * radius * radius)}`
    }
    const side = formatLength(distanceM(points[points.length - 1], hover))
    return points.length >= 2 ? `${side} · ${formatArea(areaM2([...points, hover]))}` : side
  })()
  const closing =
    tool === 'polygon' && hover && points.length >= 3 && map.latLngToContainerPoint(points[0]).distanceTo(map.latLngToContainerPoint(hover)) <= CLOSE_PX
  return (
    <>
      {live && hover && (
        <Marker position={hover} icon={labelIcon(closing ? 'Click to close the shape' : live, 'live')} interactive={false} keyboard={false} />
      )}
      {tool === 'circle' && hover && (
        <Polyline positions={[points[0], hover]} interactive={false} pathOptions={{ color, weight: 1.5, dashArray: '2 5' }} />
      )}
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

/**
 * Handles to change a drawn outline. A free shape or rectangle: drag a corner; drag the small dot in the middle of a
 * side to add a corner there; double-click or right-click a corner to remove it; drag the cross in the middle to
 * move the whole outline. A circle: drag its centre to move it and the square on its edge to resize it.
 * `onEnd` is called once per finished change (for undo).
 */
export function AreaHandles({ shape, onChange, onEnd }: { shape: Shape; onChange: (s: Shape) => void; onEnd: (s: Shape) => void }) {
  // While a side's dot or the move cross is dragged: the outline as it was when the drag began.
  const [drag, setDrag] = useState<{ kind: 'insert'; at: number; base: LatLon[] } | { kind: 'move'; from: LatLon; base: LatLon[] } | null>(null)
  // The same, read by the drag handlers (they can run before React renders the new state).
  type Drag = { kind: 'insert'; at: number; base: LatLon[] } | { kind: 'move'; from: LatLon; base: LatLon[] }
  const dragRef = useRef<Drag | null>(null)
  const start = (d: Drag) => {
    dragRef.current = d
    setDrag(d)
  }
  const latest = useRef(shape)
  latest.current = shape
  const end = () => {
    dragRef.current = null
    setDrag(null)
    onEnd(latest.current)
  }

  if (shape.kind === 'circle') {
    const edge: LatLon = [shape.centre[0], shape.centre[1] + shape.radiusM / mPerDegLon(shape.centre[0])]
    return (
      <>
        <Marker
          position={shape.centre}
          icon={MOVE_ICON}
          draggable
          title="Drag to move the circle"
          eventHandlers={{ drag: (e) => onChange({ ...shape, centre: latLon(e) }), dragend: end }}
        />
        <Marker
          position={edge}
          icon={handleIcon('radius')}
          draggable
          title="Drag to resize the circle"
          eventHandlers={{
            drag: (e) => onChange({ ...shape, radiusM: Math.max(0.5, distanceM(shape.centre, latLon(e))) }),
            dragend: end,
          }}
        />
      </>
    )
  }

  const pts = shape.points
  const ghostsFrom = drag?.kind === 'insert' ? drag.base : pts
  const remove = (i: number) => {
    if (pts.length <= 3) return
    const next: Shape = { kind: 'polygon', points: pts.filter((_, j) => j !== i) }
    onChange(next)
    onEnd(next)
  }
  return (
    <>
      {drag?.kind !== 'move' &&
        ghostsFrom.map((p, i) => (
          <Marker
            key={`g${i}`}
            position={midpoint(p, ghostsFrom[(i + 1) % ghostsFrom.length])}
            icon={GHOST_ICON}
            draggable
            title="Drag to add a corner here"
            eventHandlers={{
              dragstart: () => start({ kind: 'insert', at: i + 1, base: pts }),
              drag: (e) => {
                const d = dragRef.current
                const base = d?.kind === 'insert' ? d.base : pts
                const next = [...base.slice(0, i + 1), latLon(e), ...base.slice(i + 1)]
                onChange({ kind: 'polygon', points: next })
              },
              dragend: end,
            }}
          />
        ))}
      {pts.map((p, i) => (
        <Marker
          key={`c${i}`}
          position={p}
          icon={handleIcon('corner')}
          draggable
          title={pts.length > 3 ? `Corner ${i + 1}: drag to move, double-click or right-click to remove` : `Corner ${i + 1}: drag to move`}
          eventHandlers={{
            drag: (e) => onChange({ kind: 'polygon', points: latest.current.kind === 'polygon' ? latest.current.points.map((q, j) => (j === i ? latLon(e) : q)) : pts }),
            dragend: end,
            contextmenu: (e) => {
              L.DomEvent.preventDefault((e as L.LeafletMouseEvent).originalEvent)
              remove(i)
            },
            dblclick: () => remove(i),
          }}
        />
      ))}
      <Marker
        position={drag?.kind === 'move' ? centroid(drag.base) : centroid(pts)}
        icon={MOVE_ICON}
        draggable
        title="Drag to move the whole outline"
        eventHandlers={{
          dragstart: (e) => start({ kind: 'move', from: latLon(e), base: pts }),
          drag: (e) => {
            const d = dragRef.current
            if (d?.kind !== 'move') return
            const [lat, lon] = latLon(e)
            const [dLat, dLon] = [lat - d.from[0], lon - d.from[1]]
            onChange({ kind: 'polygon', points: d.base.map(([a, b]) => [a + dLat, b + dLon] as LatLon) })
          },
          dragend: end,
        }}
      />
    </>
  )
}

/** Each side's length at its middle and the area in the centre, so the outline can be read without the panel. */
export function AreaLabels({ shape }: { shape: Shape }) {
  const pts = outline(shape)
  if (pts.length < 3) return null
  const total = areaM2(pts)
  return (
    <>
      {shape.kind === 'circle' ? (
        <Marker
          position={[shape.centre[0], shape.centre[1] + shape.radiusM / 2 / mPerDegLon(shape.centre[0])]}
          icon={labelIcon(`r ${formatLength(shape.radiusM)}`, 'side')}
          interactive={false}
          keyboard={false}
        />
      ) : (
        pts.length <= 16 &&
        pts.map((p, i) => {
          const q = pts[(i + 1) % pts.length]
          return (
            <Marker key={i} position={midpoint(p, q)} icon={labelIcon(formatLength(distanceM(p, q)), 'side')} interactive={false} keyboard={false} />
          )
        })
      )}
      <Marker
        position={shape.kind === 'circle' ? shape.centre : centroid(pts)}
        icon={labelIcon(formatArea(total), 'area')}
        interactive={false}
        keyboard={false}
      />
    </>
  )
}

export const OUTLINE_COLORS = { ok: COLORS.survey, bad: COLORS.hazard, drawing: COLORS.amber }
