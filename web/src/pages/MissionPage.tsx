import { Fragment, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, download } from '../api'
import { useAuth } from '../auth'
import { CARD_ICONS, CardFrame, Glyph, type CardDrag } from '../components/CardFrame'
import { DetectionDetail } from '../components/DetectionDetail'
import { FlightControls } from '../components/FlightControls'
import { Select } from '../components/Select'
import { SensorTrace } from '../components/SensorTrace'
import { Splitter } from '../components/Splitter'
import { SensorBadge, SensorNote } from '../components/SensorBadge'
import { StatusBadge } from '../components/StatusBadge'
import { formatDuration } from '../format'
import { remainingS } from '../field/mapInfo'
import { useMissionLive } from '../live'
import { HeatLegend, HeatmapLayer, HEAT_SENSOR_LABELS } from '../map/HeatmapLayer'
import { SurveyMap } from '../map/SurveyMap'
import { TakeoffPoint, distanceM, insideArea } from '../map/TakeoffPoint'
import {
  DEFAULT_MISSION_LAYOUT,
  HEATMAP_PREFS,
  MAP_HEIGHT,
  SIDE_WIDTH,
  usePrefs,
  type HeatmapPref,
  type MissionCard,
  type MissionHideable,
} from '../prefs'
import {
  CATEGORY_LABELS,
  SOIL_LABELS,
  VERIFICATION_LABELS,
  type Category,
  type ConditionProfile,
  type Detection,
  type LatLon,
  type Mission,
  type MissionStatus,
  type SensorGrid,
  type UavSource,
} from '../types'

const SPEEDS = [1, 5, 10, 20]

/** What flies the survey: the simulator, PX4 SITL without a window (Docker), or PX4 SITL in Gazebo's window (WSL). */
type FlyWith = UavSource | 'gazebo'
const FLY_WITH: FlyWith[] = ['simulated', 'px4', 'gazebo']

/** What each PX4 option needs installed on the server's PC, with where to get it. */
const PX4_NEEDS: Record<'px4' | 'gazebo', { items: [string, string, string][] }> = {
  px4: {
    items: [
      ['Docker Desktop', 'https://www.docker.com/products/docker-desktop/', 'download'],
      [
        'the PX4 image (about 3.3 GB; download it once before the first flight: docker pull jonasvautherin/px4-gazebo-headless:1.17.0)',
        'https://hub.docker.com/r/jonasvautherin/px4-gazebo-headless',
        'the image page',
      ],
    ],
  },
  gazebo: {
    items: [
      ['WSL with Ubuntu 22.04', 'https://learn.microsoft.com/windows/wsl/install', 'how to install'],
      [
        'PX4-Autopilot built inside Ubuntu (once, 30–60 minutes) and WSL mirrored networking',
        'https://github.com/PX4/PX4-Autopilot',
        'source and build steps',
      ],
    ],
  },
}

/** Orange notice before a PX4 flight: what must be installed. "Don't show again" is kept per user in this browser. */
function Px4Requirements({ kind, username }: { kind: 'px4' | 'gazebo'; username: string | undefined }) {
  const key = `uav.px4Notice.v1.${username ?? ''}`
  const [hidden, setHidden] = useState(() => {
    try {
      return localStorage.getItem(key) === 'hidden'
    } catch {
      return false
    }
  })
  const [seen, setSeen] = useState(false)
  if (hidden || seen) {
    // Still reachable: a small link brings the notice back (and clears "Don't show again").
    return (
      <button
        type="button"
        className="link-button px4-notice-again"
        onClick={() => {
          setHidden(false)
          setSeen(false)
          try {
            localStorage.removeItem(key)
          } catch {
            // storage unavailable
          }
        }}
      >
        What PX4 needs
      </button>
    )
  }
  const dontShow = () => {
    setHidden(true)
    try {
      localStorage.setItem(key, 'hidden')
    } catch {
      // storage unavailable: hidden until reload
    }
  }
  return (
    <div className="px4-notice" role="note">
      <p>
        <strong>Before a PX4 flight, the server's PC needs:</strong>
      </p>
      <ul>
        {PX4_NEEDS[kind].items.map(([what, url, label]) => (
          <li key={url}>
            {what} (<a href={url} target="_blank" rel="noreferrer">{label}</a>)
          </li>
        ))}
      </ul>
      <div className="px4-notice-actions">
        <button type="button" className="button" onClick={() => setSeen(true)}>
          Got it
        </button>
        <button type="button" className="link-button" onClick={dontShow}>
          Don't show again
        </button>
      </div>
    </div>
  )
}

/** The last choice of Fly with, kept per user in this browser (it may be unavailable: then it lasts until reload). */
function useFlyWith(username: string | undefined): [FlyWith, (f: FlyWith) => void] {
  const key = `uav.flyWith.v1.${username ?? ''}`
  const [flyWith, setFlyWith] = useState<FlyWith>(() => {
    try {
      const saved = localStorage.getItem(key) as FlyWith | null
      return saved && FLY_WITH.includes(saved) ? saved : 'simulated'
    } catch {
      return 'simulated'
    }
  })
  const choose = (f: FlyWith) => {
    setFlyWith(f)
    try {
      localStorage.setItem(key, f)
    } catch {
      // storage unavailable: the choice lasts until reload
    }
  }
  return [flyWith, choose]
}
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

function Legend({
  showBaseline,
  heat,
  grid,
}: {
  showBaseline: boolean
  heat: HeatmapPref
  grid: SensorGrid | null
}) {
  return (
    <div className="legend" aria-label="Map legend">
      <span><i className="swatch swatch-high" aria-hidden="true" /> High priority</span>
      <span><i className="swatch swatch-suspect" aria-hidden="true" /> Needs verification</span>
      <span><i className="swatch swatch-clutter" aria-hidden="true" /> Likely clutter</span>
      {showBaseline && <span><i className="swatch swatch-baseline" aria-hidden="true" /> Fixed-threshold baseline</span>}
      {heat === 'off' ? (
        <span><i className="swatch swatch-swath" aria-hidden="true" /> Ground scanned</span>
      ) : (
        <HeatLegend sensor={heat} grid={grid} />
      )}
    </div>
  )
}

const HEAT_CHOICES: Record<HeatmapPref, { label: string; title: string }> = {
  md: { label: 'MD', title: HEAT_SENSOR_LABELS.md },
  gpr: { label: 'GPR', title: HEAT_SENSOR_LABELS.gpr },
  off: { label: 'Hide', title: 'No sensor heatmap' },
}
const HEATMAP_REFRESH_MS = 3000
// A page with a folded corner, for the report button.
const REPORT_ICON = 'M7 3h7l5 5v13H7z M14 3v5h5 M10 13h6 M10 17h6'

/** The mission's readings as a grid while the heatmap is on: again every few seconds while the UAV flies, and once
 * more when the flight ends. null while it loads. */
function useSensorGrid(missionId: number, on: boolean, status: MissionStatus | undefined): SensorGrid | null {
  const [grid, setGrid] = useState<SensorGrid | null>(null)
  useEffect(() => {
    if (!on || status === undefined) return
    let stopped = false
    let timer: number | undefined
    const load = () =>
      api<SensorGrid>(`/api/missions/${missionId}/heatmap`)
        .then((g) => {
          if (!stopped) setGrid(g)
        })
        .catch(() => undefined) // the map keeps the last grid; the next refresh tries again
        .finally(() => {
          if (!stopped && status === 'running') timer = window.setTimeout(load, HEATMAP_REFRESH_MS)
        })
    load()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [missionId, on, status])
  return on ? grid : null
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
  const [chosenFlyWith, setFlyWith] = useFlyWith(user?.username)
  // Whether the server can talk to PX4 at all (MAVSDK installed); whether PX4 runs shows when the survey starts.
  const [px4Available, setPx4Available] = useState(false)
  // Whether the server starts PX4 SITL (Docker) at the takeoff point by itself.
  const [px4Restarts, setPx4Restarts] = useState(false)
  // Whether the server can start PX4 SITL in Gazebo's window (WSL on its PC), and whether that is turned off.
  const [px4Gazebo, setPx4Gazebo] = useState(false)
  const [px4ManageOff, setPx4ManageOff] = useState(false)
  // A saved choice the server cannot fly (yet: its health comes after the first render) falls back to the simulator.
  const flyWith: FlyWith =
    (chosenFlyWith !== 'simulated' && !px4Available) || (chosenFlyWith === 'gazebo' && !px4Gazebo)
      ? 'simulated'
      : chosenFlyWith
  const withPx4 = flyWith !== 'simulated'
  // PX4's takeoff and landing points as last saved from this page (null: as the mission came); picking: which one
  // the next map click sets.
  const [pointsFrom, setPointsFrom] = useState<Mission | null>(null)
  const [picking, setPicking] = useState<'takeoff' | 'landing' | null>(null)
  const [pointError, setPointError] = useState<string | null>(null)
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
  // The map over the whole page; not saved, a reload shows the page as customized.
  const [expanded, setExpanded] = useState(false)
  const { prefs, setPrefs, setMissionLayout } = usePrefs()
  const layout = prefs.layout.mission
  const heat = prefs.missionLayers.heatmap
  const grid = useSensorGrid(missionId, heat !== 'off', state.mission?.status)
  const [reportBusy, setReportBusy] = useState(false)
  const [reportError, setReportError] = useState<string | null>(null)

  useEffect(() => {
    sideRef.current?.scrollTo({ top: 0 })
    // On a phone the cards sit below the map, so bring the opened detection into view.
    if (selectedId !== null && window.matchMedia('(max-width: 860px)').matches) {
      sideRef.current?.scrollIntoView({ block: 'start' })
    }
  }, [selectedId])

  useEffect(() => {
    if (!expanded) return
    // On a phone the page scrolls, so bring the bigger map into view.
    if (window.matchMedia('(max-width: 860px)').matches) gridRef.current?.scrollIntoView({ block: 'start' })
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setExpanded(false)
    }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [expanded])

  useEffect(() => {
    api<{ px4_available?: boolean; px4_restarts?: boolean; px4_gazebo?: boolean; px4_manage_off?: boolean }>(
      '/api/health',
    )
      .then((h) => {
        setPx4Available(h.px4_available === true)
        setPx4Restarts(h.px4_restarts === true)
        setPx4Gazebo(h.px4_gazebo === true)
        setPx4ManageOff(h.px4_manage_off === true)
      })
      .catch(() => setPx4Available(false))
  }, [])

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
  const remaining = remainingS(mission, t)
  const canStart = user?.role === 'supervisor' && mission.status === 'planned'
  // PX4's takeoff and landing points: chosen on the map, or by default just outside the area at the start of the
  // survey, landing back there.
  const pts = pointsFrom ?? mission
  const pathStart = mission.path[0] ?? mission.area[0]
  const pathEnd = mission.path[mission.path.length - 1] ?? pathStart
  const takeoffPoint: LatLon = pts.takeoff_point ?? pathStart
  const takeoffChosen = pts.takeoff_lat !== null
  const landingChosen = pts.landing_lat !== null
  const landingPoint: LatLon = pts.landing_point ?? takeoffPoint
  const showTakeoff = (canStart && withPx4) || (mission.status !== 'planned' && mission.uav_source === 'px4')
  const inside = (p: LatLon) => insideArea(p, mission.area)

  async function savePoint(kind: 'takeoff' | 'landing', p: LatLon | null) {
    setPicking(null)
    const from = kind === 'takeoff' ? pathStart : pathEnd
    if (p && distanceM(p, from) > 900) {
      setPointError(
        `That point is ${(distanceM(p, from) / 1000).toFixed(1)} km from the ${kind === 'takeoff' ? 'start' : 'end'} of the survey; PX4 accepts up to 900 m. Choose a point nearer the area.`,
      )
      return
    }
    setPointError(null)
    try {
      const saved = await api<Mission>(`/api/missions/${missionId}/${kind}`, {
        method: 'PUT',
        body: p ? { lat: p[0], lon: p[1] } : {},
      })
      setPointsFrom(saved)
    } catch (e) {
      setPointError(e instanceof Error ? e.message : `The ${kind} point was not saved`)
    }
  }

  async function start() {
    setStarting(true)
    setStartError(null)
    try {
      // PX4 flies in real time; the playback speed is the simulator's.
      const body = withPx4
        ? { uav_source: 'px4', gazebo: flyWith === 'gazebo' }
        : { uav_source: 'simulated', speed_factor: speedFactor }
      await api(`/api/missions/${missionId}/start`, { method: 'POST', body })
    } catch (e) {
      setStartError(e instanceof Error ? e.message : 'Could not start the survey')
    } finally {
      setStarting(false)
    }
  }

  async function downloadReport() {
    setReportBusy(true)
    setReportError(null)
    try {
      await download(`/api/missions/${missionId}/report.pdf`, `mission-${missionId}-report.pdf`)
    } catch (e) {
      setReportError(e instanceof Error ? e.message : 'The report could not be made')
    } finally {
      setReportBusy(false)
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
  // Opening a detection brings the page back, so its details show in the column.
  const select = (id: number) => {
    setSelectedId(id)
    setExpanded(false)
  }

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
        aside={<span className="small">{mission.uav_source === 'px4' ? `PX4 SITL · ${linkLabel}` : linkLabel}</span>}
        keep={
          <>
            <div className="row spread">
              <span className="outcome">
                <StatusBadge mission={mission} label="Flight" />
                <SensorBadge mission={mission} label="Sensors" />
              </span>
              <span className="num">{progress}% of path</span>
            </div>
            <div className="progress" role="progressbar" aria-valuenow={progress} aria-valuemin={0} aria-valuemax={100}>
              <div style={{ transform: `scaleX(${mission.progress})` }} />
            </div>
            {mission.error &&
              (mission.status === 'stopped' ? (
                <p className="small">{mission.error}. What was scanned is kept.</p>
              ) : (
                <p className="error">{mission.error}</p>
              ))}
            <SensorNote mission={mission} />
            {user?.role === 'supervisor' && mission.status === 'running' && <FlightControls mission={mission} />}
            {canStart && (
              <div className="start">
                <label className="field inline">
                  <span>Fly with</span>
                  <Select<FlyWith>
                    value={flyWith}
                    onChange={setFlyWith}
                    options={[
                      { value: 'simulated', label: 'Built-in simulator' },
                      {
                        value: 'px4',
                        label: px4Available ? 'PX4 SITL' : 'PX4 SITL (not installed on the server)',
                        disabled: !px4Available,
                      },
                      {
                        value: 'gazebo',
                        label: !px4Available
                          ? 'PX4 SITL + Gazebo window (not installed on the server)'
                          : px4Gazebo
                            ? 'PX4 SITL + Gazebo window'
                            : px4ManageOff
                              ? 'PX4 SITL + Gazebo window (off: PX4_MANAGE_DOCKER=0 on the server)'
                              : 'PX4 SITL + Gazebo window (needs WSL on the server)',
                        disabled: !px4Available || !px4Gazebo,
                      },
                    ]}
                  />
                </label>
                {withPx4 && <Px4Requirements kind={flyWith === 'gazebo' ? 'gazebo' : 'px4'} username={user?.username} />}
                {withPx4 && (
                  <div className="takeoff-rows">
                    <div className="takeoff-row">
                      <span className="takeoff-label">
                        <span className="takeoff-letter" aria-hidden="true">H</span> Takeoff
                      </span>
                      <span className="small">
                        {takeoffChosen
                          ? `${Math.round(distanceM(takeoffPoint, pathStart))} m from the survey start`
                          : '5 m outside the survey start'}
                      </span>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => setPicking((x) => (x === 'takeoff' ? null : 'takeoff'))}
                      >
                        {picking === 'takeoff' ? 'Cancel' : 'Set on map'}
                      </button>
                      {takeoffChosen && picking !== 'takeoff' && (
                        <button type="button" className="link-button" onClick={() => savePoint('takeoff', null)}>
                          Default
                        </button>
                      )}
                    </div>
                    <div className="takeoff-row">
                      <span className="takeoff-label">
                        <span className="takeoff-letter landing" aria-hidden="true">L</span> Landing
                      </span>
                      <span className="small">
                        {landingChosen
                          ? `${Math.round(distanceM(landingPoint, takeoffPoint))} m from takeoff`
                          : 'Same as takeoff'}
                      </span>
                      <button
                        type="button"
                        className="link-button"
                        onClick={() => setPicking((x) => (x === 'landing' ? null : 'landing'))}
                      >
                        {picking === 'landing' ? 'Cancel' : 'Set on map'}
                      </button>
                      {landingChosen && picking !== 'landing' && (
                        <button type="button" className="link-button" onClick={() => savePoint('landing', null)}>
                          Same as takeoff
                        </button>
                      )}
                    </div>
                    {picking && (
                      <p className="small takeoff-hint" role="status">
                        Click the map where PX4 should {picking === 'takeoff' ? 'take off' : 'land'}, within 900 m of the
                        survey. You can also drag the {picking === 'takeoff' ? 'H' : 'L'}.
                      </p>
                    )}
                    {!picking && (inside(takeoffPoint) || inside(landingPoint)) && (
                      <p className="small takeoff-hint takeoff-warn">
                        The {inside(takeoffPoint) ? 'takeoff' : 'landing'} point is inside the survey area, over ground
                        that may hold mines.
                      </p>
                    )}
                    {pointError && (
                      <p className="error takeoff-hint" role="alert">
                        {pointError}
                      </p>
                    )}
                  </div>
                )}
                {!withPx4 ? (
                  <label className="field inline">
                    <span>Playback speed</span>
                    <Select
                      value={speedFactor}
                      onChange={setSpeedFactor}
                      options={SPEEDS.map((s) => ({ value: s, label: s === 1 ? 'Real time' : `${s}× faster` }))}
                    />
                  </label>
                ) : (
                  <p className="small start-note">
                    PX4 flies in real time: about {Math.max(1, Math.round(mission.estimated_duration_s / 60))} min for
                    this survey.
                    {flyWith === 'gazebo'
                      ? " Gazebo's window opens on the server's computer, at the takeoff point (up to a minute the first time). Closing the window stops PX4."
                      : px4Restarts &&
                        ' If PX4 is off or elsewhere it is started at the takeoff point first (about a minute).'}
                  </p>
                )}
                <button type="button" className="button" disabled={starting} onClick={start}>
                  {starting
                    ? flyWith === 'gazebo'
                      ? 'Opening Gazebo…'
                      : flyWith === 'px4'
                        ? 'Connecting to PX4…'
                        : 'Starting'
                    : 'Start survey'}
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
            <dd className="num">{formatDuration(remaining)}</dd>
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
    <main className={`mission-page${summaryShown ? '' : ' no-summary'}${expanded ? ' map-expanded' : ''}`}>
      <header className="mp-head">
        <div className="mp-title">
          <nav className="crumb" aria-label="Breadcrumb">
            <Link to="/">All missions</Link>
            <span aria-hidden="true"> / </span>
            <span>{mission.name}</span>
          </nav>
          <h1>
            {mission.name} <StatusBadge mission={mission} />
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
            {mission.status !== 'completed' && mission.status !== 'stopped' && <span className="small"> (after the survey)</span>}
          </label>
          <div className="toggle heat-toggle" role="radiogroup" aria-label="Sensor heatmap on the map">
            <span aria-hidden="true">Heatmap</span>
            <span className="segmented compact">
              {HEATMAP_PREFS.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  role="radio"
                  aria-checked={heat === choice}
                  className={heat === choice ? 'is-on' : undefined}
                  title={HEAT_CHOICES[choice].title}
                  onClick={() => setPrefs({ missionLayers: { ...prefs.missionLayers, heatmap: choice } })}
                >
                  {HEAT_CHOICES[choice].label}
                </button>
              ))}
            </span>
          </div>
          {user?.role === 'supervisor' && mission.status !== 'planned' && (
            <button type="button" className="toggle report-button" onClick={downloadReport} disabled={reportBusy}>
              <Glyph d={REPORT_ICON} />
              {reportBusy ? 'Making report…' : 'Download report'}
            </button>
          )}
          <button
            type="button"
            className="toggle cfg-open"
            aria-pressed={editing}
            onClick={() => {
              setEditing((e) => !e)
              setSelectedId(null)
              setExpanded(false)
            }}
          >
            <Glyph d={CARD_ICONS.customize} />
            Customize{hidden.length > 0 && ` (${hidden.length} hidden)`}
          </button>
        </div>
        {reportError && (
          <p className="error" role="alert">
            {reportError}
          </p>
        )}
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
            uav={mission.status === 'running' || mission.status === 'completed' || mission.status === 'stopped' ? t : null}
            detections={visible}
            selectedId={selectedId}
            onSelect={select}
            showSwath={heat === 'off'}
          >
            {heat !== 'off' && grid && <HeatmapLayer grid={grid} sensor={heat} />}
            {showTakeoff && (
              <TakeoffPoint
                point={takeoffPoint}
                picking={picking === 'takeoff'}
                editable={canStart && withPx4}
                onPick={(p) => savePoint('takeoff', p)}
              />
            )}
            {showTakeoff && (landingChosen || picking === 'landing') && (
              <TakeoffPoint
                point={landingPoint}
                letter="L"
                picking={picking === 'landing'}
                editable={canStart && withPx4}
                onPick={(p) => savePoint('landing', p)}
              />
            )}
          </SurveyMap>
          <Legend showBaseline={showBaseline} heat={heat} grid={grid} />
          <button
            type="button"
            className="map-expand"
            aria-pressed={expanded}
            aria-label="Expand map"
            title={expanded ? 'Back to the page (Esc)' : 'Expand map'}
            onClick={() => {
              setExpanded((x) => !x)
              setEditing(false)
            }}
          >
            <Glyph d={expanded ? CARD_ICONS.shrink : CARD_ICONS.expand} />
          </button>
          {user?.role === 'supervisor' && (
            <Link className="map-expand map-3d" to={`/missions/${missionId}/3d`} aria-label="3D view" title="3D view">
              3D
            </Link>
          )}
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
            <button type="button" className="toast" onClick={() => select(toast.id)}>
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
