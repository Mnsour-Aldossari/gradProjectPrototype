import { useState, type FormEvent } from 'react'
import { Select } from '../components/Select'
import { Rectangle, useMapEvents } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { areaSize } from '../format'
import { SurveyMap } from '../map/SurveyMap'
import { COLORS } from '../theme'
import { SOIL_LABELS, type LatLon, type Mission, type SoilType } from '../types'

// 60 m x 40 m test field near Al-Kharj (same as DEMO_AREA in the backend).
const DEMO_AREA: LatLon[] = [
  [24.13968, 47.2617],
  [24.13968, 47.2623],
  [24.13932, 47.2623],
  [24.13932, 47.2617],
]

function rectangle(a: LatLon, b: LatLon): LatLon[] {
  const [n, s] = [Math.max(a[0], b[0]), Math.min(a[0], b[0])]
  const [e, w] = [Math.max(a[1], b[1]), Math.min(a[1], b[1])]
  return [
    [n, w],
    [n, e],
    [s, e],
    [s, w],
  ]
}

function AreaDrawer({ onDone }: { onDone: (area: LatLon[]) => void }) {
  const [first, setFirst] = useState<LatLon | null>(null)
  const [hover, setHover] = useState<LatLon | null>(null)
  useMapEvents({
    click(e) {
      const p: LatLon = [e.latlng.lat, e.latlng.lng]
      if (!first) setFirst(p)
      else {
        onDone(rectangle(first, p))
        setFirst(null)
      }
    },
    mousemove(e) {
      setHover([e.latlng.lat, e.latlng.lng])
    },
  })
  if (!first || !hover) return null
  return (
    <Rectangle
      bounds={[first, hover]}
      interactive={false}
      pathOptions={{ color: COLORS.amber, weight: 2, dashArray: '6 6', fillOpacity: 0.1 }}
    />
  )
}

export function NewMissionPage() {
  const navigate = useNavigate()
  const [area, setArea] = useState<LatLon[]>(DEMO_AREA)
  const [drawing, setDrawing] = useState(false)
  const [name, setName] = useState('Test field survey')
  const [soil, setSoil] = useState<SoilType>('dry_sand')
  const [altitude, setAltitude] = useState(1.5)
  const [speed, setSpeed] = useState(2)
  const [spacing, setSpacing] = useState(2)
  const [seed, setSeed] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const size = areaSize(area)
  const sizeOk = [size.width, size.height].every((v) => v >= 20 && v <= 300)
  const lines = Math.max(1, Math.ceil(size.height / spacing))
  const pathLength = lines * size.width + (lines - 1) * (size.height / lines)
  const minutes = pathLength / speed / 60

  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const mission = await api<Mission>('/api/missions', {
        method: 'POST',
        body: {
          name: name.trim(),
          area,
          altitude_m: altitude,
          speed_mps: speed,
          line_spacing_m: spacing,
          soil_type: soil,
          scenario_seed: seed.trim() === '' ? null : Number(seed),
        },
      })
      navigate(`/missions/${mission.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the mission')
      setBusy(false)
    }
  }

  return (
    <main className="mission-layout">
      <div className="map-pane">
        <SurveyMap area={area}>{drawing && <AreaDrawer onDone={(a) => { setArea(a); setDrawing(false) }} />}</SurveyMap>
        <div className="map-hint" role="status">
          {drawing ? 'Click two opposite corners of the survey area.' : 'The outlined area will be surveyed in parallel lanes.'}
        </div>
      </div>
      <aside className="side-pane">
        <form className="stack" onSubmit={submit}>
          <h1>Plan a mission</h1>
          <label className="field">
            <span>Mission name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} />
          </label>

          <div className="field">
            <span>Survey area</span>
            <p className={`area-size num${sizeOk ? '' : ' error'}`}>
              {size.width.toFixed(0)} × {size.height.toFixed(0)} m
              {!sizeOk && ' (each side must be 20 to 300 m)'}
            </p>
            <div className="row">
              <button type="button" className="button secondary" onClick={() => setDrawing((d) => !d)}>
                {drawing ? 'Cancel drawing' : 'Draw a new area'}
              </button>
              <button type="button" className="link-button" onClick={() => setArea(DEMO_AREA)}>
                Use the test field
              </button>
            </div>
          </div>

          <label className="field">
            <span>Soil type</span>
            <Select
              value={soil}
              onChange={setSoil}
              options={(Object.entries(SOIL_LABELS) as [SoilType, string][]).map(([value, label]) => ({ value, label }))}
            />
            <small>The adaptive classifier adjusts its thresholds and depth estimate to the soil.</small>
          </label>

          <div className="field-grid">
            <label className="field">
              <span>Height (m)</span>
              <input type="number" min={0.5} max={5} step={0.1} value={altitude} onChange={(e) => setAltitude(Number(e.target.value))} />
            </label>
            <label className="field">
              <span>Speed (m/s)</span>
              <input type="number" min={0.5} max={5} step={0.1} value={speed} onChange={(e) => setSpeed(Number(e.target.value))} />
            </label>
            <label className="field">
              <span>Lane spacing (m)</span>
              <input type="number" min={0.5} max={5} step={0.1} value={spacing} onChange={(e) => setSpacing(Number(e.target.value))} />
            </label>
          </div>

          <label className="field">
            <span>Scenario seed (optional)</span>
            <input inputMode="numeric" pattern="[0-9]*" value={seed} onChange={(e) => setSeed(e.target.value)} placeholder="Random" />
            <small>The same seed recreates the same simulated buried objects.</small>
          </label>

          <p className="small num">
            About {lines} lanes, {(pathLength / 1000).toFixed(2)} km of flight, {minutes.toFixed(0)} min at real speed.
          </p>
          {error && <p className="error">{error}</p>}
          <button className="button" type="submit" disabled={busy || !sizeOk}>
            {busy ? 'Creating mission' : 'Create mission'}
          </button>
        </form>
      </aside>
    </main>
  )
}
