import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Polygon } from 'react-leaflet'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { AccuracyMeter } from '../components/AccuracyMeter'
import { Select } from '../components/Select'
import { formatDuration } from '../format'
import { AreaDrawer, AreaHandles, AreaLabels, OUTLINE_COLORS, outline, type DrawTool, type Shape } from '../map/AreaEditor'
import { SurveyMap } from '../map/SurveyMap'
import { SOIL_LABELS, type AccuracyEstimate, type LatLon, type Mission, type SoilType } from '../types'

// 60 m x 40 m test field near Al-Kharj (same as DEMO_AREA in the backend).
const DEMO_AREA: LatLon[] = [
  [24.13968, 47.2617],
  [24.13968, 47.2623],
  [24.13932, 47.2623],
  [24.13932, 47.2617],
]

const TOOLS: { tool: DrawTool; label: string; key: string; icon: string; hint: string }[] = [
  { tool: 'rect', label: 'Rectangle', key: 'R', icon: 'M4 6h16v12H4z', hint: 'Click two opposite corners.' },
  { tool: 'circle', label: 'Circle', key: 'C', icon: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18', hint: 'Click the centre, then a point on the edge.' },
  {
    tool: 'polygon',
    label: 'Free shape',
    key: 'F',
    icon: 'M5 19 3 9l8-6 9 5-2 11z',
    hint: 'Click each corner; click the first corner or double-click to finish. Backspace removes the last corner.',
  },
]

const EDIT_HINT = 'Drag a corner to move it, the dot on a side to add a corner, the cross to move the whole area. Double-click or right-click a corner to remove it.'

function Glyph({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  )
}

const UNDO_ICON = 'M9 14 4 9l5-5 M4 9h10.5a5.5 5.5 0 0 1 0 11H11'
const REDO_ICON = 'M15 14l5-5-5-5 M20 9H9.5a5.5 5.5 0 0 0 0 11H13'
const FIELD_ICON = 'M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z M12 7.5a2 2 0 1 0 0 4a2 2 0 1 0 0-4'
const HISTORY_MAX = 50

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
  accuracy: AccuracyEstimate | null
}

const CHECK_DELAY_MS = 200

export function NewMissionPage() {
  const navigate = useNavigate()
  const [shape, setShape] = useState<Shape>({ kind: 'polygon', points: DEMO_AREA })
  // Every finished change to the outline, for Undo and Redo (Ctrl+Z, Ctrl+Y).
  const [history, setHistory] = useState<{ list: Shape[]; at: number }>({ list: [{ kind: 'polygon', points: DEMO_AREA }], at: 0 })
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
  const checkKey = JSON.stringify([checked, altitude, spacing, speed, soil, seedValue])
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

  function commit(s: Shape) {
    setShape(s)
    setHistory((h) => {
      const list = [...h.list.slice(0, h.at + 1), s].slice(-HISTORY_MAX)
      return { list, at: list.length - 1 }
    })
  }
  const canUndo = history.at > 0 && !tool
  const canRedo = history.at < history.list.length - 1 && !tool
  function step(by: -1 | 1) {
    const at = history.at + by
    if (at < 0 || at >= history.list.length || tool) return
    setHistory({ ...history, at })
    setShape(history.list[at])
  }

  function cancelDrawing() {
    setDraft(null)
    setCorners(0)
    setTool(null)
  }

  // Keys for the map tools; typing in a field of the form is left alone.
  const keysRef = useRef<(e: KeyboardEvent) => void>(() => undefined)
  keysRef.current = (e: KeyboardEvent) => {
    const el = e.target as HTMLElement | null
    if (el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))) return
    const mod = e.ctrlKey || e.metaKey
    const k = e.key.toLowerCase()
    if (mod && k === 'z') {
      e.preventDefault()
      step(e.shiftKey ? 1 : -1)
    } else if (mod && k === 'y') {
      e.preventDefault()
      step(1)
    } else if (!mod && !e.altKey) {
      if (k === 'escape' && tool) cancelDrawing()
      const t = TOOLS.find((x) => x.key.toLowerCase() === k)
      if (t) pick(t.tool)
    }
  }
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => keysRef.current(e)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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

  const hint = tool ? TOOLS.find((t) => t.tool === tool)!.hint : EDIT_HINT

  return (
    <main className="mission-layout">
      <div className="map-pane plan-map">
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
                commit(s)
                setDraft(null)
                setCorners(0)
                setTool(null)
              }}
              onCancel={cancelDrawing}
            />
          ) : (
            <>
              {!valid && (
                <Polygon positions={area} interactive={false} pathOptions={{ color: OUTLINE_COLORS.bad, weight: 3, fill: false }} />
              )}
              <AreaLabels shape={shape} />
              <AreaHandles shape={shape} onChange={setShape} onEnd={commit} />
            </>
          )}
        </SurveyMap>

        <div className="draw-bar" role="toolbar" aria-label="Draw the survey area">
          <div className="draw-bar-group" role="group" aria-labelledby="draw-label">
            {TOOLS.map((t) => (
              <button
                key={t.tool}
                type="button"
                className="draw-bar-tool"
                aria-pressed={tool === t.tool}
                aria-keyshortcuts={t.key}
                title={`${t.label} (${t.key})`}
                onClick={() => pick(t.tool)}
              >
                <Glyph d={t.icon} />
                <span className="draw-bar-label">{t.label}</span>
                <kbd aria-hidden="true">{t.key}</kbd>
              </button>
            ))}
          </div>
          <span className="draw-bar-sep" aria-hidden="true" />
          <div className="draw-bar-group">
            <button type="button" className="draw-bar-tool icon-only" aria-label="Undo" title="Undo (Ctrl+Z)" disabled={!canUndo} onClick={() => step(-1)}>
              <Glyph d={UNDO_ICON} />
            </button>
            <button type="button" className="draw-bar-tool icon-only" aria-label="Redo" title="Redo (Ctrl+Y)" disabled={!canRedo} onClick={() => step(1)}>
              <Glyph d={REDO_ICON} />
            </button>
            <button
              type="button"
              className="draw-bar-tool icon-only"
              aria-label="Use the test field"
              title="Use the test field"
              disabled={tool !== null}
              onClick={() => {
                commit({ kind: 'polygon', points: DEMO_AREA })
                setFitTo([...DEMO_AREA])
              }}
            >
              <Glyph d={FIELD_ICON} />
            </button>
          </div>
        </div>

        <div className={`map-hint${tool ? ' is-drawing' : ''}`} role="status">
          <span>{hint}</span>
          {tool && (
            <button type="button" className="map-hint-cancel" onClick={cancelDrawing}>
              Cancel <kbd>Esc</kbd>
            </button>
          )}
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
            <p className="small draw-note">
              {tool === 'polygon' && corners > 0
                ? `${corners} corner${corners === 1 ? '' : 's'} placed. Backspace removes the last.`
                : tool
                  ? 'Drawing on the map. Esc cancels.'
                  : 'Draw it with the tools on the map, or drag its handles.'}
            </p>

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

          {check?.accuracy && (
            <section className="field" aria-labelledby="accuracy-label">
              <span id="accuracy-label">Expected detection with these settings</span>
              <AccuracyMeter estimate={check.accuracy} compact />
              <small>
                Slower flight and closer lanes find more, but the flight takes longer.{' '}
                <Link to="/sensors">How the sensors work</Link>
              </small>
            </section>
          )}

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
