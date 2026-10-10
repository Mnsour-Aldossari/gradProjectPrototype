import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { CircleMarker, MapContainer, Marker, Polygon, Polyline, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { COLORS } from '../theme'
import type { Detection, LatLon, Telemetry } from '../types'
import { detectionIcon, uavIcon } from './icons'
import { BaseLayers, MapTools, type PastControl, PointerReadout, ScaleBar, useBaseMap } from './MapChrome'


function metresPerPixel(lat: number, zoom: number): number {
  return (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom
}

/** Ground already covered by the sensors, drawn at its true width like a marked survey lane. */
function CoverageSwath({ track, widthM }: { track: LatLon[]; widthM: number }) {
  const map = useMap()
  const [zoom, setZoom] = useState(map.getZoom())
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) })
  if (track.length < 2) return null
  const weight = Math.max(3, widthM / metresPerPixel(track[0][0], zoom))
  return (
    <Polyline
      positions={track}
      interactive={false}
      pathOptions={{ color: '#ffffff', opacity: 0.45, weight, lineCap: 'butt', lineJoin: 'round' }}
    />
  )
}

/** Space in pixels along each map edge that something drawn over the map covers. */
export interface FitPadding {
  top: number
  right: number
  bottom: number
  left: number
}

// Smallest free space the area is fitted into; with less, the default margin is used and cards may overlap it.
const MIN_FREE_PX = { x: 120, y: 90 }

/**
 * Keeps the area in view while the layout settles (the container can start at 0 x 0
 * or change size as the side panel fills), until the user pans or zooms themselves.
 * With `padding`, the area is fitted into the space those edges leave free, and refitted when they change.
 */
function FitArea({ area, padding }: { area: LatLon[]; padding?: FitPadding }) {
  const map = useMap()
  const key = area.map((p) => p.join(',')).join(';')
  const userMoved = useRef(false)
  const paddingRef = useRef(padding)
  const fitRef = useRef<() => void>(() => undefined)
  useEffect(() => {
    userMoved.current = false
    let fitting = false
    const onUserMove = () => {
      if (!fitting) userMoved.current = true
    }
    const fit = () => {
      map.invalidateSize()
      const size = map.getSize()
      if (!area.length || size.x === 0 || size.y === 0 || userMoved.current) return
      fitting = true
      const p = paddingRef.current
      const fits = p && size.x - p.left - p.right >= MIN_FREE_PX.x && size.y - p.top - p.bottom >= MIN_FREE_PX.y
      map.fitBounds(
        L.latLngBounds(area),
        fits
          ? { paddingTopLeft: [p.left, p.top], paddingBottomRight: [p.right, p.bottom], animate: false }
          : { padding: [36, 36], animate: false },
      )
      fitting = false
    }
    fitRef.current = fit
    map.on('dragstart zoomstart', onUserMove)
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(map.getContainer())
    return () => {
      observer.disconnect()
      map.off('dragstart zoomstart', onUserMove)
    }
  }, [map, key])
  const paddingKey = padding ? `${padding.top},${padding.right},${padding.bottom},${padding.left}` : ''
  useEffect(() => {
    paddingRef.current = padding
    fitRef.current()
    // paddingKey stands for padding: refit only when the numbers change, not on every new object
  }, [paddingKey])
  return null
}

interface SurveyMapProps {
  area: LatLon[]
  path?: LatLon[]
  track?: LatLon[]
  swathWidthM?: number
  uav?: Telemetry | null
  detections?: Detection[]
  selectedId?: number | null
  onSelect?: (id: number) => void
  children?: ReactNode
  className?: string
  /** Fit the area into the space left free by cards drawn over the map (field view). */
  fitPadding?: FitPadding
  /** Show each detection's number next to its marker. */
  labelDetections?: boolean
  /** What to keep in view, if not the area (an outline being edited must not refit the map at every change). */
  fitTo?: LatLon[]
  /** The white band of ground scanned; off while a sensor heatmap shows the same ground. */
  showSwath?: boolean
  /** The map's own controls (base map, fit, my position, scale, pointer position). Off where cards cover the map. */
  controls?: boolean
  /** A button for showing or hiding the other missions, which the page draws as children. */
  past?: PastControl
}

export function SurveyMap({
  area,
  path = [],
  track = [],
  swathWidthM = 2,
  uav,
  detections = [],
  selectedId,
  onSelect,
  children,
  className,
  fitPadding,
  labelDetections = false,
  fitTo,
  showSwath = true,
  controls = true,
  past,
}: SurveyMapProps) {
  const [base, setBase] = useBaseMap()
  const center = useMemo<LatLon>(() => {
    if (!area.length) return [24.1395, 47.262]
    return [area.reduce((s, p) => s + p[0], 0) / area.length, area.reduce((s, p) => s + p[1], 0) / area.length]
  }, [area])

  return (
    <MapContainer center={center} zoom={19} maxZoom={22} className={`${className ?? 'survey-map'} base-${base}`} zoomControl>
      <BaseLayers base={base} />
      <FitArea area={fitTo ?? area} padding={fitPadding} />
      {controls && (
        <>
          <MapTools area={fitTo ?? area} base={base} onBase={setBase} past={past} />
          <ScaleBar />
          <PointerReadout />
        </>
      )}

      {/* Survey area boundary, styled after red-and-white hazard marking, with a soft glow so it reads on any ground */}
      <Polygon
        positions={area}
        interactive={false}
        pathOptions={{ color: '#ffffff', weight: 7, opacity: 0.35, fill: false, className: 'area-glow' }}
      />
      <Polygon positions={area} interactive={false} pathOptions={{ color: '#ffffff', weight: 3.5, fill: false }} />
      <Polygon
        positions={area}
        interactive={false}
        pathOptions={{
          color: COLORS.hazard,
          weight: 3.5,
          dashArray: '10 10',
          fillColor: COLORS.hazard,
          fillOpacity: 0.06,
          className: 'area-line',
        }}
      />

      {/* The planned lanes, with where the UAV starts (S) and ends (E) */}
      {path.length > 1 && (
        <>
          <Polyline
            positions={path}
            interactive={false}
            pathOptions={{ color: '#ffffff', weight: 1.4, opacity: 0.7, dashArray: '2 6', lineCap: 'round', className: 'plan-line' }}
          />
          <CircleMarker
            center={path[0]}
            radius={6}
            interactive={false}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#34e3a0', fillOpacity: 1, className: 'path-end' }}
          >
            <Tooltip permanent direction="left" offset={[-8, 0]} className="path-tag path-tag-start" interactive={false}>
              S
            </Tooltip>
          </CircleMarker>
          <CircleMarker
            center={path[path.length - 1]}
            radius={6}
            interactive={false}
            pathOptions={{ color: '#ffffff', weight: 2, fillColor: '#9b8cff', fillOpacity: 1, className: 'path-end' }}
          >
            <Tooltip permanent direction="right" offset={[8, 0]} className="path-tag path-tag-end" interactive={false}>
              E
            </Tooltip>
          </CircleMarker>
        </>
      )}
      {showSwath && <CoverageSwath track={track} widthM={swathWidthM} />}
      {track.length > 1 && (
        <Polyline
          positions={track}
          interactive={false}
          pathOptions={{ color: COLORS.survey, weight: 2.2, opacity: 0.95, lineCap: 'round', lineJoin: 'round', className: 'track-line' }}
        />
      )}

      {detections.map((d) => (
        <Marker
          key={d.id}
          position={[d.lat, d.lon]}
          icon={detectionIcon(d, d.id === selectedId)}
          zIndexOffset={d.category === 'high' ? 300 : d.category === 'suspect' ? 200 : 0}
          eventHandlers={{ click: () => onSelect?.(d.id) }}
          keyboard
          title={`Detection ${d.id}`}
        >
          {labelDetections && (
            <Tooltip permanent direction="right" offset={[12, 0]} className="det-label" interactive={false}>
              #{d.id}
            </Tooltip>
          )}
        </Marker>
      ))}

      {uav && <Marker position={[uav.lat, uav.lon]} icon={uavIcon(uav.heading_deg)} interactive={false} zIndexOffset={1000} />}
      {children}
    </MapContainer>
  )
}
