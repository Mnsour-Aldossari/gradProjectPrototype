import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { CARD_ICONS, CardFrame, Glyph, type CardDrag } from '../components/CardFrame'
import { DetectionDetail } from '../components/DetectionDetail'
import { SensorTrace } from '../components/SensorTrace'
import { Splitter } from '../components/Splitter'
import { formatDuration } from '../format'
import { useMissionLive } from '../live'
import { SurveyMap } from '../map/SurveyMap'
import { DEFAULT_MISSION_LAYOUT, MAP_HEIGHT, SIDE_WIDTH, usePrefs, type MissionCard, type MissionHideable } from '../prefs'
import {
  CATEGORY_LABELS,
  SOIL_LABELS,
  STATUS_LABELS,
  VERIFICATION_LABELS,
  type Category,
  type ConditionProfile,
  type Detection,
} from '../types'

const SPEEDS = [1, 5, 10, 20]
const CATEGORY_ORDER: Category[] = ['high', 'suspect', 'clutter']

const CARD_TITLES: Record<MissionCard | MissionHideable, string> = {
  flight: 'Flight',
  sensors: 'Sensors',
  detections: 'Potential detections',
  profile: 'How the classifier adapts here',
  summary: 'Summary',
}
const HEADING_IDS: Record<MissionCard, string> = {
  flight: 'flight-heading',
  sensors: 'sensors-heading',
  detections: 'det-heading',
  profile: 'profile-heading',
}

function Legend({ showBaseline }: { showBaseline: boolean }) {
  return (
    <div className="legend" aria-label="Map legend">
      <span><i className="swatch swatch-high" aria-hidden="true" /> High priority</span>
      <span><i className="swatch swatch-suspect" aria-hidden="true" /> Needs verification</span>
      <span><i className="swatch swatch-clutter" aria-hidden="true" /> Likely clutter</span>
      {showBaseline && <span><i className="swatch swatch-baseline" aria-hidden="true" /> Fixed-threshold baseline</span>}
      <span><i className="swatch swatch-swath" aria-hidden="true" /> Ground scanned</span>
    </div>
  )
}

export function MissionPage() {
  const missionId = Number(useParams().id)
  const { user } = useAuth()
  const { state, replaceDetection, reconnect } = useMissionLive(missionId)
  const [profile, setProfile] = useState<ConditionProfile | null>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [showClutter, setShowClutter] = useState(false)
  const [showBaseline, setShowBaseline] = useState(false)
  const [speedFactor, setSpeedFactor] = useState(10)
  const [startError, setStartError] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [toast, setToast] = useState<Detection | null>(null)
  const sideRef = useRef<HTMLElement>(null)
  // Customize mode: move and hide buttons on the cards. The layout itself is saved per user (prefs.ts).
  const [editing, setEditing] = useState(false)
  const [dragId, setDragId] = useState<MissionCard | null>(null)
  const [dropAt, setDropAt] = useState<{ id: MissionCard; where: 'before' | 'after' } | null>(null)
  // Sizes while a splitter is dragged; saved when the drag ends.
  const [draftSize, setDraftSize] = useState<{ sideWidth?: number; mapHeight?: number }>({})
  const gridRef = useRef<HTMLDivElement>(null)
  const { prefs, setMissionLayout } = usePrefs()
  const layout = prefs.layout.mission

  useEffect(() => {
    sideRef.current?.scrollTo({ top: 0 })
    // On a phone the cards sit below the map, so bring the opened detection into view.
    if (selectedId !== null && window.matchMedia('(max-width: 860px)').matches) {
      sideRef.current?.scrollIntoView({ block: 'start' })
    }
  }, [selectedId])

  useEffect(() => {
    api<ConditionProfile>(`/api/missions/${missionId}/profile`).then(setProfile).catch(() => setProfile(null))
  }, [missionId])

  const latestAlert = state.alerts[0]
  useEffect(() => {
    if (!latestAlert) return
    setToast(latestAlert.detection)
    const t = window.setTimeout(() => setToast(null), 7000)
    return () => window.clearTimeout(t)
  }, [latestAlert])

  const all = useMemo(() => Object.values(state.detections), [state.detections])
  const adaptive = useMemo(() => all.filter((d) => d.method === 'adaptive'), [all])
  const baselineHigh = useMemo(() => all.filter((d) => d.method === 'baseline' && d.category === 'high'), [all])
  const visible = useMemo(
    () => [...adaptive.filter((d) => showClutter || d.category !== 'clutter'), ...(showBaseline ? baselineHigh : [])],
    [adaptive, baselineHigh, showClutter, showBaseline],
  )
  const reported = useMemo(
    () =>
      adaptive
        .filter((d) => d.category !== 'clutter')
        .sort((a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category) || b.confidence - a.confidence),
    [adaptive],
  )
  const counts = useMemo(() => {
    const c: Record<Category, number> = { high: 0, suspect: 0, clutter: 0 }
    adaptive.forEach((d) => c[d.category]++)
    return c
  }, [adaptive])

  const mission = state.mission
  if (!mission) {
    return (
      <main className="page">
        {state.connection === 'failed' ? (
          <p className="small">
            Cannot reach the mission.{' '}
            <button type="button" className="link-button" onClick={reconnect}>
              Try again
            </button>
          </p>
        ) : (
          <p className="small">{state.connection === 'closed' ? 'Cannot reach the mission. Retrying.' : 'Loading mission'}</p>
        )}
      </main>
    )
  }

  const selected = selectedId !== null ? state.detections[selectedId] : undefined
  const t = state.telemetry
  const elapsed = t?.t_s ?? 0
  const remaining = Math.max(0, mission.estimated_duration_s - elapsed)
  const canStart = user?.role === 'supervisor' && mission.status === 'planned'

  async function start() {
    setStarting(true)
    setStartError(null)
    try {
      await api(`/api/missions/${missionId}/start`, { method: 'POST', body: { speed_factor: speedFactor } })
    } catch (e) {
      setStartError(e instanceof Error ? e.message : 'Could not start the survey')
    } finally {
      setStarting(false)
    }
  }

  const progress = Math.round(mission.progress * 100)
  const linkLabel =
    state.connection === 'open' ? 'Live link connected' : state.connection === 'failed' ? 'Live link lost' : 'Reconnecting'

  // Cards that exist right now: Sensors only during the flight, the classifier notes once loaded.
  const present: Record<MissionCard | MissionHideable, boolean> = {
    flight: true,
    sensors: mission.status === 'running',
    detections: true,
    profile: profile !== null,
    summary: true,
  }
  const hidden = layout.hidden.filter((id) => present[id])
  const shown = layout.order.filter((id) => present[id] && !layout.hidden.includes(id as MissionHideable))

  /** Swaps a card with its visible neighbour, then keeps the keyboard focus on the moved card. */
  function move(id: MissionCard, step: -1 | 1) {
    const neighbour = shown[shown.indexOf(id) + step]
    if (!neighbour) return
    const order = [...layout.order]
    const a = order.indexOf(id)
    const b = order.indexOf(neighbour)
    ;[order[a], order[b]] = [order[b], order[a]]
    setMissionLayout({ order })
    requestAnimationFrame(() => {
      const card = sideRef.current?.querySelector(`[data-card="${id}"]`)
      const same = card?.querySelector<HTMLButtonElement>(step < 0 ? '.cfg-up' : '.cfg-down')
      const target =
        same && !same.disabled ? same : card?.querySelector<HTMLButtonElement>('.cfg-up:not(:disabled), .cfg-down:not(:disabled)')
      target?.focus()
    })
  }
  /** Puts the dragged card before or after the one it was dropped on. */
  function drop() {
    if (dragId && dropAt && dragId !== dropAt.id) {
      const order = layout.order.filter((c) => c !== dragId)
      order.splice(order.indexOf(dropAt.id) + (dropAt.where === 'after' ? 1 : 0), 0, dragId)
      setMissionLayout({ order })
    }
    setDragId(null)
    setDropAt(null)
  }
  const dragFor = (id: MissionCard): CardDrag | undefined =>
    editing
      ? {
          dragging: dragId === id,
          hint: dragId && dragId !== id && dropAt?.id === id ? dropAt.where : null,
          onStart: () => setDragId(id),
          onEnd: () => {
            setDragId(null)
            setDropAt(null)
          },
          onOver: (where) => {
            if (dropAt?.id !== id || dropAt.where !== where) setDropAt({ id, where })
          },
          onDrop: drop,
        }
      : undefined
  const hide = (id: MissionHideable) => setMissionLayout({ hidden: [...layout.hidden, id] })
  const show = (id: MissionHideable) => setMissionLayout({ hidden: layout.hidden.filter((h) => h !== id) })
  const fold = (id: MissionCard) =>
    setMissionLayout({
      collapsed: layout.collapsed.includes(id) ? layout.collapsed.filter((c) => c !== id) : [...layout.collapsed, id],
    })
  const frame = (id: MissionCard) => ({
    cardId: id,
    title: CARD_TITLES[id],
    headingId: HEADING_IDS[id],
    folded: layout.collapsed.includes(id),
    onFold: () => fold(id),
    editing,
    first: shown[0] === id,
    last: shown[shown.length - 1] === id,
    onMove: (step: -1 | 1) => move(id, step),
    // Flight holds Start survey and the errors, so it can fold but never hide.
    onHide: id === 'flight' ? undefined : () => hide(id),
    drag: dragFor(id),
  })
  const summaryShown = !layout.hidden.includes('summary')

  const sideWidth = draftSize.sideWidth ?? layout.sideWidth ?? SIDE_WIDTH.initial
  const mapHeight = draftSize.mapHeight ?? layout.mapHeight ?? MAP_HEIGHT.initial
  // The map keeps at least 40% of the row, however wide the column is set.
  const sideMax = Math.max(SIDE_WIDTH.min, Math.min(SIDE_WIDTH.max, Math.floor((gridRef.current?.clientWidth ?? 1e4) * 0.6)))
  const sizeVars: Record<string, string> = {}
  if (draftSize.sideWidth !== undefined || layout.sideWidth !== null) sizeVars['--side'] = `min(${sideWidth}px, 60%)`
  if (draftSize.mapHeight !== undefined || layout.mapHeight !== null) sizeVars['--map-h'] = `${mapHeight}vh`
  const resize = (key: 'sideWidth' | 'mapHeight') => ({
    onChange: (value: number, done: boolean) => {
      if (done) setMissionLayout({ [key]: value })
      setDraftSize((d) => ({ ...d, [key]: done ? undefined : value }))
    },
    onReset: () => {
      setMissionLayout({ [key]: null })
      setDraftSize((d) => ({ ...d, [key]: undefined }))
    },
  })

  const cards: Record<MissionCard, ReactNode> = {
    flight: (
      <CardFrame
        {...frame('flight')}
        aside={<span className="small">{linkLabel}</span>}
        keep={
          <>
            <div className="row spread">
              <span className={`status status-${mission.status}`}>{STATUS_LABELS[mission.status]}</span>
              <span className="num">{progress}% of path</span>
            </div>
            <div className="progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
              <div style={{ width: `${mission.progress * 100}%` }} />
            </div>
            {mission.error && <p className="error">{mission.error}</p>}
            {canStart && (
              <div className="start">
                <label className="field inline">
                  <span>Playback speed</span>
                  <select value={speedFactor} onChange={(e) => setSpeedFactor(Number(e.target.value))}>
                    {SPEEDS.map((s) => (
                      <option key={s} value={s}>
                        {s === 1 ? 'Real time' : `${s}× faster`}
                      </option>
                    ))}
                  </select>
                </label>
                <button type="button" className="button" disabled={starting} onClick={start}>
                  {starting ? 'Starting' : 'Start survey'}
                </button>
              </div>
            )}
            {mission.status === 'planned' && user?.role !== 'supervisor' && (
              <p className="small">Waiting for the supervisor to start the survey.</p>
            )}
            {startError && <p className="error">{startError}</p>}
          </>
        }
      >
        <dl className="telemetry">
          <div>
            <dt>Sensor height</dt>
            <dd className="num">{t ? `${t.relative_alt_m.toFixed(2)} m` : '–'}</dd>
          </div>
          <div>
            <dt>Ground speed</dt>
            <dd className="num">{t ? `${t.ground_speed_mps.toFixed(1)} m/s` : '–'}</dd>
          </div>
          <div>
            <dt>Battery</dt>
            <dd className={`num${t && t.battery_pct < 25 ? ' warn' : ''}`}>{t ? `${t.battery_pct}%` : '–'}</dd>
          </div>
          <div>
            <dt>Heading</dt>
            <dd className="num">{t ? `${Math.round(t.heading_deg)}°` : '–'}</dd>
          </div>
          <div>
            <dt>Flight time</dt>
            <dd className="num">{formatDuration(elapsed)}</dd>
          </div>
          <div>
            <dt>Remaining</dt>
            <dd className="num">{mission.status === 'completed' ? '0:00' : formatDuration(remaining)}</dd>
          </div>
        </dl>
      </CardFrame>
    ),
    sensors: (
      <CardFrame {...frame('sensors')}>
        <SensorTrace md={state.trace.md} gpr={state.trace.gpr} />
      </CardFrame>
    ),
    detections: (
      <CardFrame {...frame('detections')} aside={<span className="small">{reported.length} to verify</span>}>
        {reported.length === 0 ? (
          <p className="small">
            {mission.status === 'planned' ? 'Detections appear here during the survey.' : 'Nothing reported yet.'}
          </p>
        ) : (
          <ul className="det-list">
            {reported.map((d) => (
              <li key={d.id}>
                <button type="button" className={`det-${d.category}`} onClick={() => setSelectedId(d.id)}>
                  <span className={`swatch swatch-${d.category}`} aria-hidden="true" />
                  <span className="det-name">
                    #{d.id} {CATEGORY_LABELS[d.category]}
                    <span className={`det-status ver-${d.status}`}>{VERIFICATION_LABELS[d.status]}</span>
                  </span>
                  <span className="det-score num" title="Ranking score">
                    {d.confidence.toFixed(2)}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardFrame>
    ),
    profile: profile && (
      <CardFrame {...frame('profile')}>
        <ul className="notes">
          {profile.notes.map((n) => (
            <li key={n}>{n}</li>
          ))}
        </ul>
      </CardFrame>
    ),
  }

  return (
    <main className={`mission-page${summaryShown ? '' : ' no-summary'}`}>
      <header className="mp-head">
        <div className="mp-title">
          <nav className="crumb" aria-label="Breadcrumb">
            <Link to="/">All missions</Link>
            <span aria-hidden="true"> / </span>
            <span>{mission.name}</span>
          </nav>
          <h1>
            {mission.name} <span className={`status status-${mission.status}`}>{STATUS_LABELS[mission.status]}</span>
          </h1>
          <p className="small">
            {SOIL_LABELS[mission.soil_type]}, sensor height {mission.altitude_m} m, lanes every {mission.line_spacing_m} m,
            scenario seed {mission.scenario_seed}
          </p>
        </div>
        <div className="toggles">
          <label className="toggle">
            <input type="checkbox" checked={showClutter} onChange={(e) => setShowClutter(e.target.checked)} />
            Show likely clutter on the map
          </label>
          <label className="toggle">
            <input type="checkbox" checked={showBaseline} onChange={(e) => setShowBaseline(e.target.checked)} />
            Compare with the fixed-threshold baseline
            {mission.status !== 'completed' && <span className="small"> (after the survey)</span>}
          </label>
          <button
            type="button"
            className="toggle cfg-open"
            aria-pressed={editing}
            onClick={() => {
              setEditing((e) => !e)
              setSelectedId(null)
            }}
          >
            <Glyph d={CARD_ICONS.customize} />
            Customize{hidden.length > 0 && ` (${hidden.length} hidden)`}
          </button>
        </div>
        {editing && (
          <div className="cfg-bar" role="region" aria-label="Customize this page">
            <p className="small">
              Drag cards by their handle or move them with the arrows; fold or hide what you do not need. Drag the blue
              bar to resize. Saved on this device for your account.
            </p>
            {hidden.length > 0 && (
              <div className="cfg-hidden">
                <span className="small">Hidden:</span>
                {hidden.map((id) => (
                  <button key={id} type="button" className="cfg-chip" onClick={() => show(id)}>
                    + {CARD_TITLES[id]}
                  </button>
                ))}
              </div>
            )}
            <div className="cfg-actions">
              <button type="button" className="link-button" onClick={() => setMissionLayout(DEFAULT_MISSION_LAYOUT)}>
                Reset this page
              </button>
              <button type="button" className="button" onClick={() => setEditing(false)}>
                Done
              </button>
            </div>
          </div>
        )}
      </header>

      {summaryShown && (
        <div className="mp-summary">
          {editing && (
            <div className="cfg-row-head">
              <span className="small">Summary</span>
              <button type="button" className="cfg-tool" aria-label="Hide Summary" title="Hide" onClick={() => hide('summary')}>
                <Glyph d={CARD_ICONS.hide} />
              </button>
            </div>
          )}
          <section className="kpis" aria-label="Potential detections by category">
            {CATEGORY_ORDER.map((c) => (
              <div key={c} className={`kpi kpi-${c}`}>
                <span className={`kpi-icon kpi-icon-${c}`} aria-hidden="true">
                  <i className={`swatch swatch-${c}`} />
                </span>
                <span>
                  <b className="num">{counts[c]}</b>
                  {CATEGORY_LABELS[c]}
                </span>
              </div>
            ))}
            <div className="kpi kpi-progress">
              <span className="kpi-icon kpi-icon-progress" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M4 12l5 5L20 6" />
                </svg>
              </span>
              <span>
                <b className="num">{progress}%</b>
                of path · flight {formatDuration(elapsed)}
              </span>
            </div>
          </section>
        </div>
      )}

      <div className="mp-grid" ref={gridRef} style={sizeVars as CSSProperties}>
        {editing && (
          <>
            <Splitter
              axis="columns"
              label="Width of the cards column"
              value={Math.min(sideWidth, sideMax)}
              min={SIDE_WIDTH.min}
              max={sideMax}
              step={20}
              pxPerUnit={() => 1}
              {...resize('sideWidth')}
            />
            <Splitter
              axis="rows"
              label="Height of the map"
              value={mapHeight}
              min={MAP_HEIGHT.min}
              max={MAP_HEIGHT.max}
              step={5}
              pxPerUnit={() => window.innerHeight / 100}
              {...resize('mapHeight')}
            />
          </>
        )}
        <div className="card map-card">
          <SurveyMap
            area={mission.area}
            path={mission.path}
            track={state.track}
            swathWidthM={mission.line_spacing_m}
            uav={mission.status === 'running' || mission.status === 'completed' ? t : null}
            detections={visible}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
          <Legend showBaseline={showBaseline} />
          {state.connection === 'failed' ? (
            <div className="map-banner">
              Live connection lost.{' '}
              <button type="button" className="link-button" onClick={reconnect}>
                Try again
              </button>
            </div>
          ) : (
            state.connection !== 'open' && <div className="map-banner">Live connection lost. Reconnecting.</div>
          )}
          {toast && (
            <button type="button" className="toast" onClick={() => setSelectedId(toast.id)}>
              <span className="swatch swatch-high" aria-hidden="true" />
              <span>
                <strong>New high-priority potential detection</strong>
                <span className="small">Detection #{toast.id}. Open to review.</span>
              </span>
            </button>
          )}
        </div>

        <aside className="mp-col" ref={sideRef} aria-label="Mission details">
          {selected ? (
            <div className="card card-pad">
              <DetectionDetail
                detection={selected}
                onClose={() => setSelectedId(null)}
                onUpdated={replaceDetection}
              />
            </div>
          ) : (
            <>
              {shown.map((id) => (
                <Fragment key={id}>{cards[id]}</Fragment>
              ))}

              <p className="footnote">
                Simulated survey data. Every marker is a potential detection until trained personnel verify it.
              </p>
            </>
          )}
        </aside>
      </div>
    </main>
  )
}
