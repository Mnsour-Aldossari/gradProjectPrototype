import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { MapContainer, Marker, Polygon, Polyline, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import { COLORS } from '../theme'
import type { Detection, LatLon, Telemetry } from '../types'
import { detectionIcon, uavIcon } from './icons'

const SATELLITE_URL = 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'
const SATELLITE_ATTRIBUTION = 'Imagery &copy; Esri, Maxar, Earthstar Geographics'

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

/**
 * Keeps the area in view while the layout settles (the container can start at 0 x 0
 * or change size as the side panel fills), until the user pans or zooms themselves.
 */
function FitArea({ area }: { area: LatLon[] }) {
  const map = useMap()
  const key = area.map((p) => p.join(',')).join(';')
  const userMoved = useRef(false)
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
      map.fitBounds(L.latLngBounds(area), { padding: [36, 36], animate: false })
      fitting = false
    }
    map.on('dragstart zoomstart', onUserMove)
    fit()
    const observer = new ResizeObserver(fit)
    observer.observe(map.getContainer())
    return () => {
      observer.disconnect()
      map.off('dragstart zoomstart', onUserMove)
    }
  }, [map, key])
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
}: SurveyMapProps) {
  const center = useMemo<LatLon>(() => {
    if (!area.length) return [24.1395, 47.262]
    return [area.reduce((s, p) => s + p[0], 0) / area.length, area.reduce((s, p) => s + p[1], 0) / area.length]
  }, [area])

  return (
    <MapContainer center={center} zoom={19} maxZoom={22} className={className ?? 'survey-map'} zoomControl>
      <TileLayer url={SATELLITE_URL} attribution={SATELLITE_ATTRIBUTION} maxNativeZoom={19} maxZoom={22} />
      <FitArea area={area} />

      {/* Survey area boundary, styled after red-and-white hazard marking */}
      <Polygon positions={area} interactive={false} pathOptions={{ color: '#ffffff', weight: 4, fill: false }} />
      <Polygon
        positions={area}
        interactive={false}
        pathOptions={{ color: COLORS.hazard, weight: 4, dashArray: '10 10', fillColor: '#ffffff', fillOpacity: 0.04 }}
      />

      {path.length > 1 && (
        <Polyline
          positions={path}
          interactive={false}
          pathOptions={{ color: '#ffffff', weight: 1.2, opacity: 0.75, dashArray: '3 6' }}
        />
      )}
      <CoverageSwath track={track} widthM={swathWidthM} />
      {track.length > 1 && (
        <Polyline positions={track} interactive={false} pathOptions={{ color: COLORS.survey, weight: 1.4, opacity: 0.85 }} />
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
        />
      ))}

      {uav && <Marker position={[uav.lat, uav.lon]} icon={uavIcon(uav.heading_deg)} interactive={false} zIndexOffset={1000} />}
      {children}
    </MapContainer>
  )
}
