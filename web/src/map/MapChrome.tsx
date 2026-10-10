import L from 'leaflet'
import { useEffect, useRef, useState } from 'react'
import { TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { LatLon } from '../types'

/**
 * The map's own controls, drawn over it by SurveyMap: the base map (satellite, satellite with place names, a dark
 * street map), "show the whole survey area", "go to my position", a metric scale bar and the pointer's coordinates.
 */

export type BaseMap = 'satellite' | 'hybrid' | 'dark'

const BASE_KEY = 'uav.map.base'
const BASES: { id: BaseMap; label: string }[] = [
  { id: 'satellite', label: 'Satellite' },
  { id: 'hybrid', label: 'Satellite + names' },
  { id: 'dark', label: 'Dark map' },
]

const ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services'
const ESRI_ATTRIBUTION = 'Imagery &copy; Esri, Maxar, Earthstar Geographics'
const CARTO_ATTRIBUTION = '&copy; OpenStreetMap contributors &copy; CARTO'

function readBase(): BaseMap {
  try {
    const v = localStorage.getItem(BASE_KEY)
    return v === 'hybrid' || v === 'dark' ? v : 'satellite'
  } catch {
    return 'satellite'
  }
}

/** The chosen base map, remembered on this device. */
export function useBaseMap(): [BaseMap, (b: BaseMap) => void] {
  const [base, setBase] = useState<BaseMap>(readBase)
  const choose = (b: BaseMap) => {
    setBase(b)
    try {
      localStorage.setItem(BASE_KEY, b)
    } catch {
      // storage unavailable: the choice lasts until the page closes
    }
  }
  return [base, choose]
}

export function BaseLayers({ base }: { base: BaseMap }) {
  if (base === 'dark') {
    return (
      <TileLayer
        key="dark"
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
        attribution={CARTO_ATTRIBUTION}
        subdomains="abcd"
        maxNativeZoom={20}
        maxZoom={22}
      />
    )
  }
  return (
    <>
      <TileLayer
        key="sat"
        url={`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`}
        attribution={ESRI_ATTRIBUTION}
        maxNativeZoom={19}
        maxZoom={22}
      />
      {base === 'hybrid' && (
        <TileLayer
          key="names"
          url={`${ESRI}/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`}
          maxNativeZoom={19}
          maxZoom={22}
        />
      )}
    </>
  )
}

/** Clicks, drags and wheel turns on a control stay on it instead of moving the map below. */
function useIsolated<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  useEffect(() => {
    if (!ref.current) return
    L.DomEvent.disableClickPropagation(ref.current)
    L.DomEvent.disableScrollPropagation(ref.current)
  }, [])
  return ref
}

const ICONS = {
  layers: 'M12 3 2 8l10 5 10-5z M2 13l10 5 10-5 M2 17.5l10 5 10-5',
  fit: 'M4 9V4h5 M20 9V4h-5 M4 15v5h5 M20 15v5h-5 M9 12h6 M12 9v6',
  locate: 'M12 2v3 M12 19v3 M2 12h3 M19 12h3 M12 6a6 6 0 1 0 0 12a6 6 0 1 0 0-12 M12 10.5a1.5 1.5 0 1 0 0 3a1.5 1.5 0 1 0 0-3',
}

function Glyph({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

/** The buttons in the map's top-right corner. */
export function MapTools({ area, base, onBase }: { area: LatLon[]; base: BaseMap; onBase: (b: BaseMap) => void }) {
  const map = useMap()
  const ref = useIsolated<HTMLDivElement>()
  const [open, setOpen] = useState(false)
  const [locating, setLocating] = useState<'idle' | 'busy' | 'failed'>('idle')

  useEffect(() => {
    if (!open) return
    const close = (e: PointerEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    const esc = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('pointerdown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  function fit() {
    if (area.length) map.flyToBounds(L.latLngBounds(area), { padding: [48, 48], duration: 0.6 })
  }

  function locate() {
    if (!('geolocation' in navigator)) return setLocating('failed')
    setLocating('busy')
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setLocating('idle')
        map.flyTo([p.coords.latitude, p.coords.longitude], Math.max(map.getZoom(), 18), { duration: 0.8 })
      },
      () => setLocating('failed'),
      { enableHighAccuracy: true, timeout: 10_000 },
    )
  }

  return (
    <div className="map-tools" ref={ref}>
      <div className="map-tool-group">
        <button
          type="button"
          className="map-tool"
          aria-expanded={open}
          aria-label="Base map"
          title="Base map"
          onClick={() => setOpen((o) => !o)}
        >
          <Glyph d={ICONS.layers} />
        </button>
        {area.length > 0 && (
          <button type="button" className="map-tool" aria-label="Show the whole survey area" title="Show the whole survey area" onClick={fit}>
            <Glyph d={ICONS.fit} />
          </button>
        )}
        <button
          type="button"
          className={`map-tool${locating === 'busy' ? ' is-busy' : ''}${locating === 'failed' ? ' is-failed' : ''}`}
          aria-label="Go to my position"
          title={locating === 'failed' ? 'Your position is not available (location permission or signal)' : 'Go to my position'}
          onClick={locate}
        >
          <Glyph d={ICONS.locate} />
        </button>
      </div>
      {open && (
        <div className="map-base-menu" role="radiogroup" aria-label="Base map">
          {BASES.map((b) => (
            <button
              key={b.id}
              type="button"
              role="radio"
              aria-checked={base === b.id}
              className={`map-base map-base-${b.id}`}
              onClick={() => {
                onBase(b.id)
                setOpen(false)
              }}
            >
              <span className="map-base-swatch" aria-hidden="true" />
              {b.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

/** Leaflet's metric scale bar, bottom right. */
export function ScaleBar() {
  const map = useMap()
  useEffect(() => {
    const scale = L.control.scale({ metric: true, imperial: false, position: 'bottomright', maxWidth: 110 })
    scale.addTo(map)
    return () => {
      scale.remove()
    }
  }, [map])
  return null
}

/** Where the pointer is, for a mouse; hidden on touch screens (redesign.css). */
export function PointerReadout() {
  const [at, setAt] = useState<L.LatLng | null>(null)
  useMapEvents({
    mousemove: (e) => setAt(e.latlng),
    mouseout: () => setAt(null),
  })
  if (!at) return null
  return (
    <div className="map-readout" aria-hidden="true">
      {at.lat.toFixed(6)}, {at.lng.toFixed(6)}
    </div>
  )
}
