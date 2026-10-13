import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { ImageOverlay, useMap, useMapEvents } from 'react-leaflet'
import type { SensorGrid } from '../types'

export type HeatSensor = 'md' | 'gpr'

export const HEAT_SENSOR_LABELS: Record<HeatSensor, string> = {
  md: 'Metal detector',
  gpr: 'Ground-penetrating radar',
}

// One hue, light to dark: weak readings stay pale and let the imagery through, strong ones are dark and opaque.
// Blue, so it never reads as a detection category (red, amber, grey markers). It sits on satellite imagery, so it is
// the same in the light and dark themes.
const STOPS = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']
const RGB = STOPS.map((hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16)))

/** Position on the colour scale for a normalized value: square root, so the soil's weak background still shows. */
export function heatPosition(value: number): number {
  return Math.sqrt(Math.min(1, Math.max(0, value)))
}

export function heatRgba(value: number): [number, number, number, number] {
  const t = heatPosition(value) * (RGB.length - 1)
  const i = Math.min(RGB.length - 2, Math.floor(t))
  const f = t - i
  const [r, g, b] = RGB[i].map((c, k) => Math.round(c + (RGB[i + 1][k] - c) * f))
  return [r, g, b, Math.round(255 * (0.5 + 0.45 * heatPosition(value)))]
}

/** CSS gradient of the scale, for the legend. */
export const HEAT_GRADIENT = `linear-gradient(to right, ${STOPS.join(', ')})`

/** The grid as an image, one pixel per cell; cells without a reading are transparent. */
function gridImage(grid: SensorGrid, sensor: HeatSensor): string | null {
  const canvas = document.createElement('canvas')
  canvas.width = grid.cols
  canvas.height = grid.rows
  const ctx = canvas.getContext('2d')
  if (!ctx) return null
  const image = ctx.createImageData(grid.cols, grid.rows)
  grid[sensor].forEach((value, i) => {
    if (value === null) return
    image.data.set(heatRgba(value), i * 4)
  })
  ctx.putImageData(image, 0, 0)
  return canvas.toDataURL()
}

/** The value under the pointer, in a small tooltip. */
function HoverValue({ grid, sensor }: { grid: SensorGrid; sensor: HeatSensor }) {
  const map = useMap()
  const tip = useMemo(() => L.tooltip({ direction: 'top', offset: [0, -8], className: 'heat-tip' }), [])
  useEffect(() => () => void tip.remove(), [tip])
  useMapEvents({
    mousemove(e) {
      const [[south, west], [north, east]] = grid.bounds
      const col = Math.floor(((e.latlng.lng - west) / (east - west)) * grid.cols)
      const row = Math.floor(((north - e.latlng.lat) / (north - south)) * grid.rows)
      const value = col >= 0 && col < grid.cols && row >= 0 && row < grid.rows ? grid[sensor][row * grid.cols + col] : null
      if (value === null) {
        tip.remove()
        return
      }
      tip.setLatLng(e.latlng).setContent(`${HEAT_SENSOR_LABELS[sensor]}: ${value.toFixed(2)}`)
      if (!map.hasLayer(tip)) tip.addTo(map)
    },
    mouseout() {
      tip.remove()
    },
  })
  return null
}

const PANE = 'heatmap'

/** One sensor's readings over the map, under the lanes, the track and the markers. */
export function HeatmapLayer({ grid, sensor }: { grid: SensorGrid; sensor: HeatSensor }) {
  const map = useMap()
  // Above the imagery (tiles: 200), below the lines and markers (overlays: 400). Made once and kept, so turning
  // the layer off and on again reuses it.
  if (!map.getPane(PANE)) {
    const pane = map.createPane(PANE)
    pane.style.zIndex = '350'
    pane.style.pointerEvents = 'none'
  }
  const url = useMemo(() => gridImage(grid, sensor), [grid, sensor])
  const bounds = useMemo(() => L.latLngBounds(grid.bounds), [grid.bounds])
  if (!url) return null
  return (
    <>
      <ImageOverlay url={url} bounds={bounds} pane={PANE} className="heatmap-img" interactive={false} />
      <HoverValue grid={grid} sensor={sensor} />
    </>
  )
}

/** The scale in the map legend: what the colours mean, and that the data is simulated. */
export function HeatLegend({ sensor, grid }: { sensor: HeatSensor; grid: SensorGrid | null }) {
  return (
    <span className="heat-key">
      <span className="heat-key-name">{HEAT_SENSOR_LABELS[sensor]}</span>
      <span className="heat-key-scale">
        <i className="heat-key-bar" style={{ background: HEAT_GRADIENT }} aria-hidden="true" />
        <span className="heat-key-ticks" aria-hidden="true">
          <span>0</span>
          <span style={{ left: `${heatPosition(0.25) * 100}%` }}>0.25</span>
          <span style={{ left: '100%' }}>1</span>
        </span>
      </span>
      <span className="heat-key-note">
        {grid === null
          ? 'Loading readings'
          : grid.readings === 0
            ? 'No readings yet'
            : `Strongest reading per cell, normalized: 1 is a reading of ${grid.full_scale[sensor].toFixed(1)} or more. Simulated data.`}
      </span>
    </span>
  )
}
