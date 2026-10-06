import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Polygon } from 'react-leaflet'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { Select } from '../components/Select'
import { formatDuration } from '../format'
import { AreaDrawer, AreaHandles, OUTLINE_COLORS, outline, type DrawTool, type Shape } from '../map/AreaEditor'
import { SurveyMap } from '../map/SurveyMap'
import { SOIL_LABELS, type LatLon, type Mission, type SoilType } from '../types'

// 60 m x 40 m test field near Al-Kharj (same as DEMO_AREA in the backend).
const DEMO_AREA: LatLon[] = [
  [24.13968, 47.2617],
  [24.13968, 47.2623],
  [24.13932, 47.2623],
  [24.13932, 47.2617],
]

const TOOLS: { tool: DrawTool; label: string; hint: string }[] = [
  { tool: 'rect', label: 'Rectangle', hint: 'Click two opposite corners.' },
  { tool: 'circle', label: 'Circle', hint: 'Click the centre, then a point on the edge.' },
  {
    tool: 'polygon',
    label: 'Free shape',
    hint: 'Click each corner; click the first corner or double-click to finish. Backspace removes the last corner.',
  },
]

/** The backend's verdict on an outline (POST /api/missions/check). */
interface AreaCheck {
  ok: boolean
  problems: string[]
  path: LatLon[]
  path_length_m: number
  width_m: number
  height_m: number
  area_m2: number
  estimated_duration_s: number
}

const CHECK_DELAY_MS = 200

export function NewMissionPage() {
  const navigate = useNavigate()
  const [shape, setShape] = useState<Shape>({ kind: 'polygon', points: DEMO_AREA })
  // What the map keeps in view: the test field until the user moves the map (editing never refits it).
  const [fitTo, setFitTo] = useState<LatLon[]>(DEMO_AREA)
  const [tool, setTool] = useState<DrawTool | null>(null)
  // While drawing: the outline so far (to the pointer), and how many corners are placed.
  const [draft, setDraft] = useState<LatLon[] | null>(null)
  const [corners, setCorners] = useState(0)
  const [name, setName] = useState('Test field survey')
  const [soil, setSoil] = useState<SoilType>('dry_sand')
  const [altitude, setAltitude] = useState(1.5)
  const [speed, setSpeed] = useState(2)
  const [spacing, setSpacing] = useState(2)
  const [seed, setSeed] = useState('')
  const [check, setCheck] = useState<AreaCheck | null>(null)
  const [checkError, setCheckError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const checkSeq = useRef(0)

  const area = outline(shape)
  const checked = draft ?? area
  const seedValue = seed.trim() === '' ? null : Number(seed)

  // Ask the backend about the outline as it changes: the same rules as Create mission, and the lanes it would get.
  const checkKey = JSON.stringify([checked, spacing, speed, soil, seedValue])
  useEffect(() => {
    const seq = ++checkSeq.current
    const timer = window.setTimeout(() => {
      api<AreaCheck>('/api/missions/check', {
        method: 'POST',
        body: {
          area: checked,
          altitude_m: altitude,
          speed_mps: speed,
          line_spacing_m: spacing,
          soil_type: soil,
          scenario_seed: Number.isInteger(seedValue) ? seedValue : null,
        },
      })
        .then((c) => {
          if (seq !== checkSeq.current) return
          setCheck(c)
          setCheckError(null)
        })
        .catch((e) => {
          if (seq !== checkSeq.current) return
          setCheck(null)
          setCheckError(e instanceof Error ? e.message : 'The outline could not be checked')
        })
    }, CHECK_DELAY_MS)
    return () => window.clearTimeout(timer)
    // checkKey covers every input of the check.
  }, [checkKey])

  const valid = check !== null && check.ok && !checkError
  const color = tool && corners > 0 ? (valid ? OUTLINE_COLORS.drawing : OUTLINE_COLORS.bad) : valid ? OUTLINE_COLORS.ok : OUTLINE_COLORS.bad
  const lanes = check ? Math.round(check.path.length / 2) : 0

  function pick(t: DrawTool) {
    setDraft(null)
    setCorners(0)
    setTool((cur) => (cur === t ? null : t))
  }

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
          scenario_seed: seedValue,
        },
      })
      navigate(`/missions/${mission.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the mission')
      setBusy(false)
    }
  }

  const hint = tool ? TOOLS.find((t) => t.tool === tool)!.hint : 'Drag the handles to change the outline.'

  return (
    <main className="mission-layout">
      <div className="map-pane">
        <SurveyMap area={tool ? [] : area} path={check?.path ?? []} fitTo={fitTo}>
          {tool ? (
            <AreaDrawer
              tool={tool}
              color={color}
              onDraft={(d, n) => {
                setDraft(d)
                setCorners(n)
              }}
              onDone={(s) => {
                setShape(s)
                setDraft(null)
                setCorners(0)
                setTool(null)
              }}
              onCancel={() => {
                setDraft(null)
                setCorners(0)
                setTool(null)
              }}
            />
          ) : (
            <>
              {!valid && (
                <Polygon positions={area} interactive={false} pathOptions={{ color: OUTLINE_COLORS.bad, weight: 3, fill: false }} />
              )}
              <AreaHandles shape={shape} onChange={setShape} onEnd={() => {}} />
            </>
          )}
        </SurveyMap>
        <div className="map-hint" role="status">
          {hint}
        </div>
      </div>
      <aside className="side-pane">
        <form className="stack" onSubmit={submit}>
          <h1>Plan a mission</h1>
          <label className="field">
            <span>Mission name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={120} autoComplete="off" />
          </label>

          <div className="field">
            <span id="draw-label">Survey area</span>
            <div className="draw-tools" role="group" aria-labelledby="draw-label">
              {TOOLS.map((t) => (
                <button key={t.tool} type="button" aria-pressed={tool === t.tool} onClick={() => pick(t.tool)}>
                  {t.label}
                </button>
              ))}
            </div>
            <div className="row">
              {tool === 'polygon' && corners > 0 && (
                <span className="small">
                  {corners} corner{corners === 1 ? '' : 's'} placed. Backspace removes the last.
                </span>
              )}
              {tool && (
                <button type="button" className="link-button" onClick={() => pick(tool)}>
                  Cancel drawing
                </button>
              )}
              {!tool && (
                <button
                  type="button"
                  className="link-button"
                  onClick={() => {
                    setShape({ kind: 'polygon', points: DEMO_AREA })
                    setFitTo([...DEMO_AREA])
                  }}
                >
                  Use the test field
                </button>
              )}
            </div>

            <div className={`area-check ${valid ? 'ok' : 'bad'}`} aria-live="polite">
              {checkError ? (
                <p>{checkError}</p>
              ) : !check ? (
                <p className="small">Checking the outline…</p>
              ) : check.ok ? (
                <>
                  <p className="area-check-title">
                    <span aria-hidden="true">✓</span> {tool && corners > 0 ? 'This outline works' : 'Ready to survey'}
                  </p>
                  <p className="small num">
                    {check.width_m.toFixed(0)} × {check.height_m.toFixed(0)} m, {(check.area_m2 / 10_000).toFixed(2)} ha ·{' '}
                    {lanes} lanes, {(check.path_length_m / 1000).toFixed(2)} km · about{' '}
                    {formatDuration(check.estimated_duration_s)} at real speed
                  </p>
                </>
              ) : (
                <>
                  <p className="area-check-title">
                    <span aria-hidden="true">✗</span> {tool && corners > 0 ? 'Not yet a valid outline' : 'Change the outline'}
                  </p>
                  <ul>
                    {check.problems.map((p) => (
                      <li key={p}>{p}.</li>
                    ))}
                  </ul>
                </>
              )}
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

          {error && <p className="error">{error}</p>}
          <button className="button" type="submit" disabled={busy || tool !== null || !valid}>
            {busy ? 'Creating mission…' : 'Create mission'}
          </button>
        </form>
      </aside>
    </main>
  )
}
