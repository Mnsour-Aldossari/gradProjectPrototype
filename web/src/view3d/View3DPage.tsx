import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { DetectionDetail } from '../components/DetectionDetail'
import { FlightControls } from '../components/FlightControls'
import { Select } from '../components/Select'
import { SensorBadge } from '../components/SensorBadge'
import { StatusBadge } from '../components/StatusBadge'
import { laneProgress, remainingS } from '../field/mapInfo'
import { formatDuration } from '../format'
import { useMissionLive } from '../live'
import { usePrefs } from '../prefs'
import {
  CATEGORY_LABELS,
  VERIFICATION_LABELS,
  type Category,
  type Detection,
  type LatLon,
  type Telemetry,
  type VerificationStatus,
} from '../types'
import { toXY, type Frame } from './geo'
import { countAt, poseAt, revealTime, type Pose } from './replay'
import { World, type CameraMode, type Layer } from './scene'

const REPLAY_SPEEDS = [1, 5, 10, 20]
const CAMERAS: { mode: CameraMode; label: string }[] = [
  { mode: 'orbit', label: '3D Orbit' },
  { mode: 'top', label: 'Top-down' },
  { mode: 'follow', label: 'Follow UAV' },
]
const CATEGORY_ORDER: Category[] = ['high', 'suspect', 'clutter']
const VERIFY: VerificationStatus[] = ['confirmed_by_team', 'false_alarm', 'pending']

type LayerKey = Layer | 'clutter'
const LAYERS: { key: LayerKey; label: string; swatch: string }[] = [
  { key: 'flown', label: 'Flown path', swatch: 'sw-flown' },
  { key: 'planned', label: 'Planned lanes', swatch: 'sw-planned' },
  { key: 'scanned', label: 'Scanned area', swatch: 'sw-scanned' },
  { key: 'footprint', label: 'Sensor footprint', swatch: 'sw-footprint' },
  { key: 'buffers', label: 'Safety buffers', swatch: 'sw-buffer' },
  { key: 'clutter', label: 'Likely clutter', swatch: 'sw-clutter' },
  { key: 'imagery', label: 'Terrain imagery', swatch: 'sw-imagery' },
]
const DEFAULT_LAYERS: Record<LayerKey, boolean> = {
  flown: true,
  planned: true,
  scanned: true,
  footprint: true,
  buffers: true,
  clutter: false,
  imagery: false,
}
const SCALE_STEPS = [1, 2, 5, 10, 20, 50, 100, 200]

interface StoredPoint {
  t_s: number
  lat: number
  lon: number
  relative_alt_m: number
  heading_deg: number
  ground_speed_mps: number
  battery_pct: number
  waypoint_seq?: number
}

function toPose(frame: Frame, p: StoredPoint | Telemetry): Pose {
  const [x, y] = toXY(frame, p.lat, p.lon)
  return {
    t: p.t_s,
    x,
    y,
    alt: p.relative_alt_m,
    heading: p.heading_deg,
    speed: p.ground_speed_mps,
    battery: p.battery_pct,
    seq: p.waypoint_seq,
  }
}

/** The whole stored track, page by page. */
async function loadTrack(missionId: number): Promise<StoredPoint[]> {
  const all: StoredPoint[] = []
  for (;;) {
    const after = all.length ? all[all.length - 1].t_s : -1
    const page = await api<StoredPoint[]>(`/api/missions/${missionId}/telemetry?after_t=${after}&limit=20000`)
    all.push(...page)
    if (page.length < 20000) return all
  }
}

/** Layer choices, kept per user in this browser (it may be unavailable: then they last until reload). */
function useLayers(username: string | undefined): [Record<LayerKey, boolean>, (k: LayerKey) => void] {
  const key = `uav.view3d.layers.v1.${username ?? ''}`
  const [layers, setLayers] = useState<Record<LayerKey, boolean>>(() => {
    try {
      // Only the known layers, and only true/false: whatever else is in storage is ignored.
      const stored: unknown = JSON.parse(localStorage.getItem(key) ?? '{}')
      const saved = typeof stored === 'object' && stored !== null ? (stored as Record<string, unknown>) : {}
      return Object.fromEntries(
        (Object.keys(DEFAULT_LAYERS) as LayerKey[]).map((k) => [k, typeof saved[k] === 'boolean' ? saved[k] : DEFAULT_LAYERS[k]]),
      ) as Record<LayerKey, boolean>
    } catch {
      return DEFAULT_LAYERS
    }
  })
  const toggle = (k: LayerKey) =>
    setLayers((l) => {
      const next = { ...l, [k]: !l[k] }
      try {
        localStorage.setItem(key, JSON.stringify(next))
      } catch {
        // storage unavailable: the choice lasts until reload
      }
      return next
    })
  return [layers, toggle]
}

/** The live sensor signal: metal detector and radar, each scaled to its own range over the last 30 s. */
function SignalChart({ md, gpr }: { md: number[]; gpr: number[] }) {
  const w = 264
  const h = 48
  const line = (values: number[]) => {
    const max = Math.max(0.05, ...values)
    return values.map((v, i) => `${((i / Math.max(1, values.length - 1)) * w).toFixed(1)},${(h - 3 - (v / max) * (h - 8)).toFixed(1)}`).join(' ')
  }
  return (
    <svg className="v3d-signal" viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" role="img" aria-label="Metal detector and radar over the last 30 seconds">
      {md.length > 1 && <polyline points={line(md)} className="sig-md" vectorEffect="non-scaling-stroke" />}
      {gpr.length > 1 && <polyline points={line(gpr)} className="sig-gpr" vectorEffect="non-scaling-stroke" />}
    </svg>
  )
}

/**
 * The survey in 3D, for the supervisor, after the "Mission view" design: a top bar with the cameras and the flight
 * commands, a Mission panel (coverage, figures, live signal, layers), a Detections panel, a timeline with the
 * detections on it, compass, zoom and scale, and labels over the scene. Live while the survey flies; a replay once it
 * has ended. A visual view only: the flight is the simulator's or PX4's, the detections are the same as on the map.
 */
export default function View3DPage() {
  const id = Number(useParams().id)
  if (!Number.isInteger(id) || id < 1) {
    return (
      <main className="v3d v3d-empty">
        <p role="alert">
          That mission address is not valid. <Link to="/">Back to the missions</Link>
        </p>
      </main>
    )
  }
  return <View3DPageFor missionId={id} />
}

function View3DPageFor({ missionId }: { missionId: number }) {
  const { user } = useAuth()
  const { state, replaceDetection, reconnect } = useMissionLive(missionId)
  usePrefs() // the panels follow the user's theme
  const holder = useRef<HTMLDivElement>(null)
  const world = useRef<World | null>(null)
  const poses = useRef<Pose[]>([])
  const lastWall = useRef(0)
  const [webglError, setWebglError] = useState(false)
  const [trackReady, setTrackReady] = useState(false)
  const [trackCount, setTrackCount] = useState(0) // re-renders as live poses arrive
  const [camera, setCamera] = useState<CameraMode>('orbit')
  const [layers, toggleLayer] = useLayers(user?.username)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [fullDetail, setFullDetail] = useState(false)
  const [verifyError, setVerifyError] = useState<string | null>(null)
  const [toast, setToast] = useState<Detection | null>(null)
  const [toastHeld, setToastHeld] = useState(false) // the pointer or keyboard focus is on it: it stays
  const [replayT, setReplayT] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(10)
  const [panel, setPanel] = useState<'mission' | 'detections' | null>(null) // on narrow screens
  // Over-the-scene elements moved every frame without re-rendering.
  const labelEls = useRef(new Map<string, HTMLDivElement>())
  const labelSpots = useRef<{ key: string; x: number; y: number; h: number }[]>([])
  const compass = useRef<SVGGElement>(null)
  const scaleBar = useRef<HTMLDivElement>(null)
  const scaleText = useRef<HTMLSpanElement>(null)
  const page = useRef<HTMLElement>(null)
  const topBar = useRef<HTMLElement>(null)

  const mission = state.mission
  const ended = mission?.status === 'completed' || mission?.status === 'stopped' || mission?.status === 'failed'
  const live = mission?.status === 'running'

  // The scene, once the mission (its area, path and PX4 points) is known.
  const areaKey = mission ? JSON.stringify([mission.area, mission.uav_source, mission.takeoff_point, mission.landing_point]) : null
  useEffect(() => {
    if (!mission || !holder.current) return
    let w: World
    try {
      const px4 = mission.uav_source === 'px4'
      const takeoff: LatLon | null = px4 ? (mission.takeoff_point ?? null) : null
      const landing: LatLon | null = px4 && mission.landing_lat !== null ? (mission.landing_point ?? null) : null
      w = new World(holder.current, mission.area, mission.path, mission.line_spacing_m, takeoff, landing)
    } catch {
      setWebglError(true)
      return
    }
    w.onPick = (id) => {
      setSelectedId(id)
      setFullDetail(false)
    }
    w.onFrame = () => {
      // Labels follow what they mark; compass and scale bar follow the camera.
      for (const s of labelSpots.current) {
        const el = labelEls.current.get(s.key)
        if (!el) continue
        const p = s.key === 'uav' ? w.dronePose() : null
        const spot = p ? w.project(p.x, p.y, p.alt) : w.project(s.x, s.y, s.h)
        if (spot) {
          el.style.transform = `translate(${spot.x.toFixed(1)}px, ${spot.y.toFixed(1)}px)`
          el.style.visibility = 'visible'
        } else el.style.visibility = 'hidden'
      }
      compass.current?.setAttribute('transform', `rotate(${(-w.azimuth()).toFixed(1)} 22 22)`)
      const mpp = w.metresPerPixel()
      const metres = SCALE_STEPS.find((m) => m / mpp >= 60) ?? SCALE_STEPS[SCALE_STEPS.length - 1]
      if (scaleBar.current) scaleBar.current.style.width = `${Math.min(160, metres / mpp).toFixed(0)}px`
      if (scaleText.current && scaleText.current.textContent !== `${metres} m`) scaleText.current.textContent = `${metres} m`
    }
    world.current = w
    poses.current = []
    setTrackReady(false)
    let cancelled = false
    loadTrack(missionId)
      .then((points) => {
        if (cancelled) return
        // Live frames that came in meanwhile go after the stored ones.
        const stored = points.map((p) => toPose(w.frame, p))
        const lastStored = stored.length ? stored[stored.length - 1].t : -Infinity
        poses.current = [...stored, ...poses.current.filter((p) => p.t > lastStored)]
        w.resetTrack() // live frames drawn so far now sit after the stored track
        setTrackReady(true)
        setTrackCount(poses.current.length)
      })
      .catch(() => !cancelled && setTrackReady(true))
    return () => {
      cancelled = true
      w.dispose()
      world.current = null
    }
    // The scene depends on the area and the PX4 points only; other mission fields change during the flight.
  }, [areaKey, missionId])

  // Layers to the scene.
  useEffect(() => {
    const w = world.current
    if (!w) return
    for (const l of LAYERS) if (l.key !== 'clutter') w.setLayer(l.key, layers[l.key])
  }, [layers, trackReady])

  // Follow the UAV by default while it flies.
  const startedLive = useRef(false)
  useEffect(() => {
    if (live && !startedLive.current) {
      startedLive.current = true
      setCamera('follow')
    }
  }, [live])

  useEffect(() => {
    world.current?.setCamera(camera)
  }, [camera, trackReady])

  // Live frames: add to the track and glide the UAV there.
  const t = state.telemetry
  useEffect(() => {
    const w = world.current
    if (!w || !t || ended) return
    const list = poses.current
    if (list.length && t.t_s <= list[list.length - 1].t) return
    const pose = toPose(w.frame, t)
    list.push(pose)
    const now = performance.now()
    const glide = lastWall.current ? Math.min(400, Math.max(50, now - lastWall.current)) : 0
    lastWall.current = now
    w.setDrone(pose, glide)
    w.setTrack(list, list.length)
    setTrackCount(list.length)
  }, [t, ended])

  // Live: show the stored track and the UAV at its last position once loaded.
  useEffect(() => {
    const w = world.current
    if (!w || !trackReady || ended) return
    const list = poses.current
    w.setTrack(list, list.length)
    if (list.length) w.setDrone(list[list.length - 1], 0)
  }, [trackReady, ended])

  // Replay of an ended survey: starts at the end, showing everything.
  const first = poses.current[0]?.t ?? 0
  const lastT = poses.current.length ? poses.current[poses.current.length - 1].t : 0
  useEffect(() => {
    if (ended && trackReady) {
      setReplayT((r) => (r === null ? lastT : r))
      setCamera((c) => (c === 'follow' ? 'orbit' : c))
    }
  }, [ended, trackReady, lastT])

  useEffect(() => {
    const w = world.current
    if (!w || replayT === null || !ended || !poses.current.length) return
    w.setTrack(poses.current, countAt(poses.current, replayT))
    w.setDrone(poseAt(poses.current, replayT), 0)
  }, [replayT, ended, trackCount])

  useEffect(() => {
    if (!playing) return
    let frame = 0
    let prev = performance.now()
    const tick = (now: number) => {
      const dt = (now - prev) / 1000
      prev = now
      setReplayT((r) => {
        const next = Math.min(lastT, (r ?? first) + dt * speed)
        if (next >= lastT) setPlaying(false)
        return next
      })
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, speed, first, lastT])

  // When the UAV first passed each detection: for the timeline, and in a replay for when its pin appears.
  const adaptive = useMemo(() => Object.values(state.detections).filter((d) => d.method === 'adaptive'), [state.detections])
  const reveal = useMemo(() => {
    const w = world.current
    const m = new Map<number, number>()
    if (!w || !trackReady || !mission || !poses.current.length) return m
    const reach = Math.max(1, mission.line_spacing_m / 2)
    for (const d of adaptive) {
      const [x, y] = toXY(w.frame, d.lat, d.lon)
      m.set(d.id, revealTime(poses.current, x, y, reach))
    }
    return m
    // trackCount: the live track grows.
  }, [adaptive, trackReady, mission, trackCount])
  const visible = useMemo(
    () =>
      adaptive
        .filter(
          (d) =>
            (layers.clutter || d.category !== 'clutter') &&
            (replayT === null || !ended || (reveal.get(d.id) ?? 0) <= replayT),
        )
        .sort((a, b) => CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category) || b.confidence - a.confidence),
    [adaptive, layers.clutter, replayT, ended, reveal],
  )
  const markersShown = useRef(false)
  useEffect(() => {
    const w = world.current
    if (!w || !trackReady) return
    w.setMarkers(
      visible.map((d) => {
        const [x, y] = toXY(w.frame, d.lat, d.lon)
        return { id: d.id, x, y, category: d.category }
      }),
      markersShown.current && (live || playing),
    )
    markersShown.current = true
  }, [visible, trackReady, live, playing])

  useEffect(() => {
    world.current?.selectMarker(selectedId)
  }, [selectedId, trackReady])

  // Panels and buttons start below the top bar, which wraps to more lines on narrow screens.
  const hasMission = mission !== null
  useEffect(() => {
    const bar = topBar.current
    if (!bar) return
    const place = () => page.current?.style.setProperty('--v3d-below-top', `${bar.offsetHeight + 14}px`)
    const observer = new ResizeObserver(place)
    observer.observe(bar)
    place()
    return () => observer.disconnect()
  }, [hasMission])

  const latestAlert = state.alerts[0]
  useEffect(() => {
    if (!latestAlert) return
    setToast(latestAlert.detection)
    setToastHeld(false)
  }, [latestAlert])
  useEffect(() => {
    if (!toast || toastHeld) return
    const timer = window.setTimeout(() => setToast(null), 7000)
    return () => window.clearTimeout(timer)
  }, [toast, toastHeld])

  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setSelectedId(null)
        setPanel(null)
      }
    }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [])

  if (!mission) {
    return (
      <main className="v3d v3d-empty">
        {state.connection === 'failed' ? (
          <p role="alert">
            Cannot reach the mission.{' '}
            <button type="button" className="link-button" onClick={reconnect}>
              Try again
            </button>
          </p>
        ) : (
          <p role="status">Loading mission…</p>
        )}
      </main>
    )
  }

  const w = world.current
  // In a replay the selected detection shows only once the UAV has found it.
  const selected = selectedId !== null && visible.some((d) => d.id === selectedId) ? state.detections[selectedId] : undefined
  const replaying = ended && replayT !== null && poses.current.length > 0
  const pose = replaying ? poseAt(poses.current, replayT) : t && w ? toPose(w.frame, t) : null
  const height = pose?.alt
  const groundSpeed = pose?.speed
  const battery = pose?.battery
  const lanesTotal = Math.floor((t?.waypoint_total ?? mission.path.length) / 2)
  const lane = replaying
    ? pose?.seq !== undefined
      ? Math.min(lanesTotal, Math.floor(pose.seq / 2) + 1)
      : null
    : laneProgress(mission, t).lane
  // In a replay: waypoints reached so far (the end of a completed survey is all of it).
  const coverage = replaying
    ? mission.status === 'completed' && (replayT ?? 0) >= lastT
      ? 1
      : Math.min(1, Math.max(0, (pose?.seq ?? 1) - 1) / Math.max(1, mission.path.length - 1))
    : mission.status === 'completed'
      ? 1
      : mission.progress
  const remaining = replaying ? Math.max(0, lastT - (replayT ?? 0)) : remainingS(mission, t)
  const elapsed = replaying ? (replayT ?? first) - first : t ? t.t_s : 0
  const total = replaying ? lastT - first : live ? (t?.t_s ?? 0) + remainingS(mission, t) : lastT - first
  const counts: Record<Category, number> = { high: 0, suspect: 0, clutter: 0 }
  adaptive.forEach((d) => counts[d.category]++)

  const xyOf = (d: Detection): [number, number] => (w ? toXY(w.frame, d.lat, d.lon) : [0, 0])
  const fromUav = (d: Detection) => {
    if (!pose) return null
    const [x, y] = xyOf(d)
    return Math.round(Math.hypot(x - pose.x, y - pose.y))
  }
  const whenSeen = (d: Detection) => {
    const r = reveal.get(d.id)
    return r === undefined ? null : formatDuration(r - first)
  }

  // Labels over the scene: the UAV and the reported detections (and the selected one, whatever its category).
  const labelled = visible.filter((d) => d.category !== 'clutter' || d.id === selectedId).slice(0, 12)
  labelSpots.current = [
    ...(pose ? [{ key: 'uav', x: 0, y: 0, h: 0 }] : []),
    ...labelled.map((d) => {
      const [x, y] = xyOf(d)
      return { key: `d${d.id}`, x, y, h: 1.9 }
    }),
  ]
  const labelRef = (key: string) => (el: HTMLDivElement | null) => {
    if (el) labelEls.current.set(key, el)
    else labelEls.current.delete(key)
  }

  function pick(d: Detection) {
    setSelectedId(d.id)
    setFullDetail(false)
    const [x, y] = xyOf(d)
    world.current?.focus(x, y)
  }

  async function verify(d: Detection, status: VerificationStatus) {
    setVerifyError(null)
    try {
      replaceDetection(await api<Detection>(`/api/detections/${d.id}`, { method: 'PATCH', body: { status, notes: d.notes } }))
    } catch (e) {
      setVerifyError(e instanceof Error ? e.message : 'Could not save the verification')
    }
  }

  const evidence = (d: Detection) => {
    const md = typeof d.features.md_evidence === 'number' && d.features.md_evidence >= 1
    const gpr = typeof d.features.gpr_evidence === 'number' && d.features.gpr_evidence >= 1
    return md && gpr ? 'Metal + radar' : md ? 'Metal' : gpr ? 'Radar' : 'Weak'
  }

  return (
    <main className={`v3d${panel ? ` panel-${panel}` : ''}`} ref={page}>
      <div className="v3d-canvas" ref={holder} />
      <div className="v3d-vignette" aria-hidden="true" />
      {webglError && (
        <div className="v3d-message">
          <p>This browser cannot show 3D graphics (WebGL is off or not supported).</p>
          <Link className="button" to={`/missions/${missionId}`}>
            Back to the Map
          </Link>
        </div>
      )}

      {/* Labels over the scene */}
      <div className="v3d-labels" aria-hidden="true">
        {pose && (
          <div className="v3d-label v3d-label-uav" ref={labelRef('uav')}>
            <span className="v3d-label-head">UAV{lane !== null ? ` · Lane ${lane}` : ''}</span>
            <span className="num">
              {height !== undefined ? `${height.toFixed(1)} m AGL` : '–'} · {groundSpeed !== undefined ? `${groundSpeed.toFixed(1)} m/s` : '–'}
            </span>
          </div>
        )}
        {labelled.map((d) => (
          <div key={d.id} className={`v3d-label v3d-label-${d.category}${d.id === selectedId ? ' selected' : ''}`} ref={labelRef(`d${d.id}`)}>
            <span className="v3d-label-head num">#{d.id}</span>
            {d.id === selectedId && <span className="v3d-label-cat">{CATEGORY_LABELS[d.category]}</span>}
            <span className="num">{d.confidence.toFixed(2)}</span>
          </div>
        ))}
      </div>

      {/* Top bar */}
      <header className="v3d-top" ref={topBar}>
        <Link className="v3d-back" to={`/missions/${missionId}`} aria-label="Back to the mission page">
          <svg viewBox="0 0 26 26" aria-hidden="true">
            <rect x="5" y="5" width="16" height="16" rx="2" transform="rotate(45 13 13)" />
            <circle cx="13" cy="13" r="3" />
          </svg>
          <span>Mission</span>
        </Link>
        <span className="v3d-divider" aria-hidden="true" />
        <div className="v3d-title">
          <h1>{mission.name}</h1>
          <span className="small">
            Lawnmower · {lanesTotal} lanes · {mission.line_spacing_m} m spacing · {mission.uav_source === 'px4' ? 'PX4 SITL' : 'Simulator'}
            {live && state.connection !== 'open' ? ' · Reconnecting…' : ''}
          </span>
        </div>
        <span className="outcome">
          <StatusBadge mission={mission} label="Flight" />
          <SensorBadge mission={mission} label="Sensors" />
        </span>
        <span className="v3d-grow" />
        <div className="v3d-seg" role="group" aria-label="Camera">
          {CAMERAS.map((c) => (
            <button
              key={c.mode}
              type="button"
              aria-pressed={camera === c.mode}
              disabled={c.mode === 'follow' && !live && !replaying}
              onClick={() => {
                setCamera(c.mode)
                world.current?.setCamera(c.mode)
              }}
            >
              {c.label}
            </button>
          ))}
        </div>
        <span className="v3d-grow" />
        <span className="v3d-clock num">T+ {formatDuration(elapsed)}</span>
        <div className="v3d-panel-toggles">
          <button type="button" aria-pressed={panel === 'mission'} onClick={() => setPanel((p) => (p === 'mission' ? null : 'mission'))}>
            Mission
          </button>
          <button
            type="button"
            aria-pressed={panel === 'detections'}
            onClick={() => setPanel((p) => (p === 'detections' ? null : 'detections'))}
          >
            Detections
          </button>
        </div>
        {live && (
          <div className="v3d-commands">
            <FlightControls mission={mission} />
          </div>
        )}
      </header>

      {/* A region that is always on the page, so a screen reader announces the detection when it appears */}
      <div role="alert" aria-atomic="true">
        {toast && (
          <button
            type="button"
            className="toast v3d-toast"
            onClick={() => setSelectedId(toast.id)}
            onMouseEnter={() => setToastHeld(true)}
            onMouseLeave={() => setToastHeld(false)}
            onFocus={() => setToastHeld(true)}
            onBlur={() => setToastHeld(false)}
          >
            <span className="swatch swatch-high" aria-hidden="true" />
            <span>
              <strong>New high-priority potential detection</strong>
              <span className="small">Detection #{toast.id}. Open to review.</span>
            </span>
          </button>
        )}
      </div>

      {/* Mission panel */}
      <aside className="v3d-panel v3d-left" aria-label="Mission">
        <section className="v3d-block">
          <div className="v3d-row">
            <span className="v3d-caps">Area coverage</span>
            <span className="v3d-big num">{Math.round(coverage * 100)}%</span>
          </div>
          <div className="v3d-bar" aria-hidden="true">
            <div style={{ transform: `scaleX(${coverage})` }} />
          </div>
          <span className="small num">
            {lane !== null ? `Lane ${lane} of ${lanesTotal}` : `${lanesTotal} lanes`}
            {mission.status === 'planned' ? ' · not started' : ` · ${replaying ? 'left in replay' : 'ETA'} ${formatDuration(remaining)}`}
          </span>
        </section>

        <div className="v3d-tiles">
          <div>
            <span>Height</span>
            <strong className="num">{height !== undefined ? `${height.toFixed(2)} m` : '–'}</strong>
          </div>
          <div>
            <span>Ground speed</span>
            <strong className="num">{groundSpeed !== undefined ? `${groundSpeed.toFixed(1)} m/s` : '–'}</strong>
          </div>
          <div>
            <span>Battery</span>
            <strong className={`num${battery !== undefined ? (battery < 25 ? ' bad' : ' good') : ''}`}>
              {battery !== undefined ? `${Math.round(battery)}%` : '–'}
            </strong>
          </div>
          <div>
            <span>Source</span>
            <strong>{mission.uav_source === 'px4' ? 'PX4 SITL' : 'Simulator'}</strong>
          </div>
        </div>

        <section className="v3d-block">
          <div className="v3d-row">
            <span className="v3d-caps">Sensor signal</span>
            <span className="small">
              <i className="v3d-key sig-md" /> Metal <i className="v3d-key sig-gpr" /> Radar
            </span>
          </div>
          {live ? (
            <SignalChart md={state.trace.md} gpr={state.trace.gpr} />
          ) : (
            <p className="small v3d-note">The signal shows live while the survey flies.</p>
          )}
        </section>

        <section className="v3d-block">
          <span className="v3d-caps">Layers</span>
          <ul className="v3d-layers">
            {LAYERS.map((l) => (
              <li key={l.key}>
                <button type="button" role="switch" aria-checked={layers[l.key]} onClick={() => toggleLayer(l.key)}>
                  <span className={`v3d-swatch ${l.swatch}`} aria-hidden="true" />
                  <span className="v3d-grow">{l.label}</span>
                  <span className="v3d-switch" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      </aside>

      {/* Detections panel */}
      <aside className="v3d-panel v3d-right" aria-label="Detections">
        <div className="v3d-row">
          <h2>Detections</h2>
          <span className="v3d-chips">
            <span className="v3d-chip high">{counts.high} High priority</span>
            <span className="v3d-chip suspect">{counts.suspect} To verify</span>
          </span>
        </div>
        {visible.length === 0 ? (
          <p className="small v3d-note">{mission.status === 'planned' ? 'Detections appear here during the survey.' : 'Nothing reported yet.'}</p>
        ) : (
          <ul className="v3d-detections">
            {visible.map((d) => {
              const far = fromUav(d)
              const seen = whenSeen(d)
              return (
                <li key={d.id}>
                  <button type="button" className={`v3d-det${d.id === selectedId ? ' selected' : ''}`} onClick={() => pick(d)}>
                    <span className={`v3d-diamond ${d.category}`} aria-hidden="true" />
                    <span className="v3d-det-body">
                      <span className="v3d-row">
                        <span className="num v3d-det-id">#{d.id}</span>
                        <span className="num">{d.confidence.toFixed(2)}</span>
                      </span>
                      <span className="v3d-meter" aria-hidden="true">
                        <span className={d.category} style={{ width: `${Math.round(Math.min(1, d.confidence) * 100)}%` }} />
                      </span>
                      <span className="small">
                        {CATEGORY_LABELS[d.category]}
                        {far !== null ? ` · ${far} m from UAV` : ''}
                        {seen ? ` · ${seen}` : ''}
                      </span>
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}

        {selected && (
          <section className={`v3d-card ${selected.category}`} aria-label={`Detection ${selected.id}`}>
            {fullDetail ? (
              <DetectionDetail detection={selected} onClose={() => setFullDetail(false)} onUpdated={replaceDetection} />
            ) : (
              <>
                <div className="v3d-row">
                  <span className="num v3d-card-id">#{selected.id}</span>
                  <span className={`v3d-card-cat ${selected.category}`}>{CATEGORY_LABELS[selected.category]}</span>
                </div>
                <dl className="v3d-card-grid">
                  <div>
                    <dt>Score</dt>
                    <dd className="num">{selected.confidence.toFixed(2)}</dd>
                  </div>
                  <div>
                    <dt>Est. depth</dt>
                    <dd className="num">{selected.est_depth_m !== null ? `${Math.round(selected.est_depth_m * 100)} cm` : '–'}</dd>
                  </div>
                  <div>
                    <dt>Evidence</dt>
                    <dd>{evidence(selected)}</dd>
                  </div>
                  <div>
                    <dt>Status</dt>
                    <dd>{VERIFICATION_LABELS[selected.status]}</dd>
                  </div>
                </dl>
                <span className="small num">
                  {selected.lat.toFixed(5)}° N, {selected.lon.toFixed(5)}° E
                </span>
                <div className="v3d-verify" role="group" aria-label="Verification">
                  {VERIFY.map((s) => (
                    <button
                      key={s}
                      type="button"
                      aria-pressed={selected.status === s}
                      className={s === 'confirmed_by_team' ? 'primary' : ''}
                      onClick={() => verify(selected, s)}
                    >
                      {VERIFICATION_LABELS[s]}
                    </button>
                  ))}
                </div>
                {verifyError && (
                  <p className="error" role="alert">
                    {verifyError}
                  </p>
                )}
                <div className="v3d-row">
                  <button type="button" className="link-button" onClick={() => setFullDetail(true)}>
                    Full details
                  </button>
                  <button type="button" className="link-button" onClick={() => setSelectedId(null)}>
                    Close
                  </button>
                </div>
                <p className="small v3d-note">A potential detection. Trained personnel must verify it before any conclusion.</p>
              </>
            )}
          </section>
        )}
      </aside>

      {/* Compass, zoom and scale */}
      <div className="v3d-compass" title="North">
        <svg viewBox="0 0 44 44" aria-label="Compass">
          <circle cx="22" cy="22" r="19" />
          <g ref={compass}>
            <path className="north" d="M22 6 L27 22 L22 20 L17 22 Z" />
            <path className="south" d="M22 38 L27 22 L22 24 L17 22 Z" />
            <text x="22" y="5" textAnchor="middle">
              N
            </text>
          </g>
        </svg>
      </div>
      <div className="v3d-view-buttons">
        <button type="button" aria-label="Zoom in" title="Zoom in" onClick={() => world.current?.zoom(0.75)}>
          <svg viewBox="0 0 18 18" aria-hidden="true">
            <path d="M9 3v12M3 9h12" />
          </svg>
        </button>
        <button type="button" aria-label="Zoom out" title="Zoom out" onClick={() => world.current?.zoom(1.33)}>
          <svg viewBox="0 0 18 18" aria-hidden="true">
            <path d="M3 9h12" />
          </svg>
        </button>
        <button type="button" aria-label="Fit survey area" title="Fit survey area" onClick={() => world.current?.fit()}>
          <svg viewBox="0 0 18 18" aria-hidden="true">
            <path d="M2 6V2h4M12 2h4v4M16 12v4h-4M6 16H2v-4" />
          </svg>
        </button>
        <button
          type="button"
          className="accent"
          aria-label="Recenter on UAV"
          title="Recenter on UAV"
          disabled={!pose}
          onClick={() => world.current?.recenter()}
        >
          <svg viewBox="0 0 18 18" aria-hidden="true">
            <circle cx="9" cy="9" r="5" />
            <circle cx="9" cy="9" r="1.5" className="fill" />
            <path d="M9 1v3M9 14v3M1 9h3M14 9h3" />
          </svg>
        </button>
      </div>
      <div className="v3d-scale" aria-hidden="true">
        <div ref={scaleBar} />
        <span ref={scaleText} className="num">
          10 m
        </span>
      </div>

      {/* Timeline and legend */}
      <footer className="v3d-bottom" aria-label="Timeline">
        <div className="v3d-timeline">
          {replaying ? (
            <button
              type="button"
              className="v3d-play"
              aria-label={playing ? 'Pause replay' : 'Play replay'}
              onClick={() => {
                if (!playing && (replayT ?? 0) >= lastT) setReplayT(first)
                setPlaying((p) => !p)
              }}
            >
              <svg viewBox="0 0 14 14" aria-hidden="true">
                {playing ? <path d="M3 2h3v10H3zM8 2h3v10H8z" /> : <path d="M3 1.5v11l9-5.5z" />}
              </svg>
            </button>
          ) : (
            <span className={`v3d-live${live ? ' on' : ''}`}>{live ? 'LIVE' : mission.status === 'planned' ? 'PLANNED' : 'NO TRACK'}</span>
          )}
          <span className="num v3d-time">{formatDuration(elapsed)}</span>
          <div className="v3d-scrub">
            <div className="v3d-scrub-track" />
            <div className="v3d-scrub-fill" style={{ width: `${total > 0 ? Math.min(100, (elapsed / total) * 100) : 0}%` }} />
            {adaptive
              .filter((d) => d.category !== 'clutter' && reveal.has(d.id) && total > 0)
              .map((d) => (
                <span
                  key={d.id}
                  className={`v3d-tick ${d.category}`}
                  style={{ left: `${Math.min(100, ((reveal.get(d.id)! - first) / total) * 100)}%` }}
                  title={`#${d.id} at ${formatDuration(reveal.get(d.id)! - first)}`}
                />
              ))}
            {replaying && (
              <input
                type="range"
                aria-label="Replay time"
                min={first}
                max={lastT}
                step={0.2}
                value={replayT ?? lastT}
                onChange={(e) => setReplayT(Number(e.target.value))}
              />
            )}
            {!replaying && total > 0 && <span className="v3d-scrub-thumb" style={{ left: `${Math.min(100, (elapsed / total) * 100)}%` }} />}
          </div>
          <span className="num v3d-time dim">{formatDuration(total)}</span>
          {replaying && (
            <label className="v3d-speed">
              <span className="sr-only">Replay speed</span>
              <Select value={speed} onChange={setSpeed} options={REPLAY_SPEEDS.map((s) => ({ value: s, label: `${s}×` }))} />
            </label>
          )}
        </div>
        <div className="v3d-legend">
          <span>
            <i className="lg-flown" /> Flown path
          </span>
          <span>
            <i className="lg-planned" /> Planned lane
          </span>
          <span>
            <i className="lg-scanned" /> Scanned area
          </span>
          <span>
            <i className="v3d-diamond high" /> High priority
          </span>
          <span>
            <i className="v3d-diamond suspect" /> Needs verification
          </span>
          <span>
            <i className="lg-buffer" /> Safety buffer (5 m, display only)
          </span>
        </div>
      </footer>
      <p className="v3d-credit small">Visual view of the survey{layers.imagery ? ' · Imagery © Esri, Maxar, Earthstar Geographics' : ''}</p>
    </main>
  )
}
