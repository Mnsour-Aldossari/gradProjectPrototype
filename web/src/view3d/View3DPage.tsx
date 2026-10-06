import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { DetectionDetail } from '../components/DetectionDetail'
import { FlightControls } from '../components/FlightControls'
import { Select } from '../components/Select'
import { StatusBadge } from '../components/StatusBadge'
import { remainingS } from '../field/mapInfo'
import { formatDuration } from '../format'
import { useMissionLive } from '../live'
import { usePrefs } from '../prefs'
import type { Category, Detection, LatLon, Telemetry } from '../types'
import { toXY, type Frame } from './geo'
import { countAt, poseAt, revealTime, type Pose } from './replay'
import { World, type CameraMode } from './scene'

const REPLAY_SPEEDS = [1, 5, 10, 20]
const CAMERA_LABELS: Record<CameraMode, string> = { follow: 'Follow', orbit: 'Orbit', top: 'Top' }

interface StoredPoint {
  t_s: number
  lat: number
  lon: number
  relative_alt_m: number
  heading_deg: number
  ground_speed_mps: number
  battery_pct: number
}

function toPose(frame: Frame, p: StoredPoint | Telemetry): Pose {
  const [x, y] = toXY(frame, p.lat, p.lon)
  return { t: p.t_s, x, y, alt: p.relative_alt_m, heading: p.heading_deg, speed: p.ground_speed_mps, battery: p.battery_pct }
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

function isDark(): boolean {
  return document.documentElement.dataset.theme === 'dark'
}

/**
 * The survey in 3D, for the supervisor: the UAV over the satellite ground, the track it flew, the ground scanned and
 * pins where potential detections were reported. Live while the survey flies; a replay once it has ended.
 * A visual view only: the flight itself is the simulator's or PX4's, and the detections are the same as on the map.
 */
export default function View3DPage() {
  const missionId = Number(useParams().id)
  const { state, replaceDetection, reconnect } = useMissionLive(missionId)
  const { prefs } = usePrefs()
  const holder = useRef<HTMLDivElement>(null)
  const world = useRef<World | null>(null)
  const poses = useRef<Pose[]>([])
  const lastWall = useRef(0)
  const [webglError, setWebglError] = useState(false)
  const [trackReady, setTrackReady] = useState(false)
  const [trackCount, setTrackCount] = useState(0) // re-renders as live poses arrive
  const [camera, setCamera] = useState<CameraMode>('orbit')
  const [showClutter, setShowClutter] = useState(false)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [toast, setToast] = useState<Detection | null>(null)
  const [replayT, setReplayT] = useState<number | null>(null)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(10)

  const mission = state.mission
  const ended = mission?.status === 'completed' || mission?.status === 'stopped' || mission?.status === 'failed'
  const live = mission?.status === 'running'

  // The scene, once the mission (its area and path) is known.
  const areaKey = mission ? JSON.stringify([mission.area, mission.uav_source, mission.takeoff_point, mission.landing_point]) : null
  useEffect(() => {
    if (!mission || !holder.current) return
    let w: World
    try {
      // PX4's takeoff pad, and its landing pad when it lands elsewhere.
      const px4 = mission.uav_source === 'px4'
      const takeoff: LatLon | null = px4 ? (mission.takeoff_point ?? null) : null
      const landing: LatLon | null = px4 && mission.landing_lat !== null ? (mission.landing_point ?? null) : null
      w = new World(holder.current, mission.area, mission.path, mission.line_spacing_m, takeoff, landing)
    } catch {
      setWebglError(true)
      return
    }
    w.onPick = (id) => setSelectedId(id)
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
        setTrackReady(true)
        setTrackCount(poses.current.length)
      })
      .catch(() => !cancelled && setTrackReady(true))
    return () => {
      cancelled = true
      w.dispose()
      world.current = null
    }
    // The scene depends on the area only; other mission fields change during the flight.
  }, [areaKey, missionId])

  // Follow the UAV by default while it flies; look at the whole area otherwise.
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

  useEffect(() => {
    world.current?.setDark(isDark())
  }, [prefs.theme, trackReady])
  useEffect(() => {
    const q = window.matchMedia('(prefers-color-scheme: dark)')
    const update = () => world.current?.setDark(isDark())
    q.addEventListener('change', update)
    return () => q.removeEventListener('change', update)
  }, [])

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

  // Pins for the reported detections (adaptive; likely clutter on request). In a replay, from when the UAV passed.
  const adaptive = useMemo(() => Object.values(state.detections).filter((d) => d.method === 'adaptive'), [state.detections])
  const reveal = useMemo(() => {
    const w = world.current
    const m = new Map<number, number>()
    if (!w || !ended || !trackReady || !mission) return m
    const reach = Math.max(1, mission.line_spacing_m / 2)
    for (const d of adaptive) {
      const [x, y] = toXY(w.frame, d.lat, d.lon)
      m.set(d.id, revealTime(poses.current, x, y, reach))
    }
    return m
  }, [adaptive, ended, trackReady, mission])
  const visible = useMemo(
    () =>
      adaptive.filter(
        (d) =>
          (showClutter || d.category !== 'clutter') &&
          (replayT === null || !ended || (reveal.get(d.id) ?? 0) <= replayT),
      ),
    [adaptive, showClutter, replayT, ended, reveal],
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

  const latestAlert = state.alerts[0]
  useEffect(() => {
    if (!latestAlert) return
    setToast(latestAlert.detection)
    const timer = window.setTimeout(() => setToast(null), 7000)
    return () => window.clearTimeout(timer)
  }, [latestAlert])

  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setSelectedId(null)
    }
    document.addEventListener('keydown', escape)
    return () => document.removeEventListener('keydown', escape)
  }, [])

  if (!mission) {
    return (
      <main className="view3d view3d-empty">
        {state.connection === 'failed' ? (
          <p>
            Cannot reach the mission.{' '}
            <button type="button" className="link-button" onClick={reconnect}>
              Try again
            </button>
          </p>
        ) : (
          <p>Loading mission…</p>
        )}
      </main>
    )
  }

  const selected = selectedId !== null ? state.detections[selectedId] : undefined
  const replaying = ended && replayT !== null && poses.current.length > 0
  const pose = replaying ? poseAt(poses.current, replayT) : null
  const counts: Record<Category, number> = { high: 0, suspect: 0, clutter: 0 }
  visible.forEach((d) => counts[d.category]++)

  return (
    <main className="view3d">
      <div className="view3d-canvas" ref={holder} />
      {webglError && (
        <div className="view3d-message">
          <p>This browser cannot show 3D graphics (WebGL is off or not supported).</p>
          <Link className="button" to={`/missions/${missionId}`}>
            Back to the Map
          </Link>
        </div>
      )}

      <header className="view3d-top">
        <Link className="button secondary" to={`/missions/${missionId}`}>
          ← Mission
        </Link>
        <h1>
          <span>{mission.name}</span> <StatusBadge mission={mission} />
        </h1>
        <span className="small view3d-source">
          {mission.uav_source === 'px4' ? 'PX4 SITL' : 'Simulator'}
          {live && state.connection !== 'open' ? ' · Reconnecting…' : ''}
        </span>
      </header>

      <div className="view3d-tools">
        <div className="view3d-seg" role="group" aria-label="Camera">
          {(['follow', 'orbit', 'top'] as CameraMode[]).map((m) => (
            <button
              key={m}
              type="button"
              aria-pressed={camera === m}
              disabled={m === 'follow' && !live && !replaying}
              onClick={() => {
                setCamera(m)
                world.current?.setCamera(m)
              }}
            >
              {CAMERA_LABELS[m]}
            </button>
          ))}
        </div>
        <label className="view3d-check">
          <input type="checkbox" checked={showClutter} onChange={(e) => setShowClutter(e.target.checked)} />
          Likely clutter
        </label>
      </div>

      {toast && (
        <button type="button" className="toast" onClick={() => setSelectedId(toast.id)}>
          <span className="swatch swatch-high" aria-hidden="true" />
          <span>
            <strong>New high-priority potential detection</strong>
            <span className="small">Detection #{toast.id}. Open to review.</span>
          </span>
        </button>
      )}

      {selected && (
        <aside className="view3d-detail card card-pad" aria-label="Detection">
          <DetectionDetail detection={selected} onClose={() => setSelectedId(null)} onUpdated={replaceDetection} />
        </aside>
      )}

      <section className="view3d-hud" aria-label="Flight">
        <dl className="view3d-figures">
          <div>
            <dt>Height</dt>
            <dd className="num">{pose ? pose.alt.toFixed(2) : t ? t.relative_alt_m.toFixed(2) : '–'} m</dd>
          </div>
          <div>
            <dt>Speed</dt>
            <dd className="num">{pose ? pose.speed.toFixed(1) : t ? t.ground_speed_mps.toFixed(1) : '–'} m/s</dd>
          </div>
          <div>
            <dt>Battery</dt>
            <dd className="num">{pose ? Math.round(pose.battery) : t ? t.battery_pct : '–'}%</dd>
          </div>
          {replaying ? (
            <div>
              <dt>Flight time</dt>
              <dd className="num">
                {formatDuration((replayT ?? 0) - first)} / {formatDuration(lastT - first)}
              </dd>
            </div>
          ) : (
            <>
              <div>
                <dt>Path</dt>
                <dd className="num">{Math.round(mission.progress * 100)}%</dd>
              </div>
              <div>
                <dt>Remaining</dt>
                <dd className="num">{formatDuration(remainingS(mission, t))}</dd>
              </div>
            </>
          )}
          <div>
            <dt>Detections</dt>
            <dd className="num view3d-counts">
              <span title="High priority">
                <i className="swatch swatch-high" aria-hidden="true" /> {counts.high}
              </span>
              <span title="Needs verification">
                <i className="swatch swatch-suspect" aria-hidden="true" /> {counts.suspect}
              </span>
            </dd>
          </div>
        </dl>

        {live && <FlightControls mission={mission} />}
        {mission.status === 'planned' && (
          <p className="small view3d-note">The survey has not started. Start it from the mission page.</p>
        )}
        {mission.status === 'stopped' && mission.error && <p className="small view3d-note">{mission.error}.</p>}

        {replaying && (
          <div className="view3d-replay">
            <button
              type="button"
              className="button"
              aria-label={playing ? 'Pause replay' : 'Play replay'}
              onClick={() => {
                if (!playing && (replayT ?? 0) >= lastT) setReplayT(first)
                setPlaying((p) => !p)
              }}
            >
              {playing ? 'Pause' : 'Replay'}
            </button>
            <input
              type="range"
              aria-label="Replay time"
              min={first}
              max={lastT}
              step={0.2}
              value={replayT ?? lastT}
              onChange={(e) => setReplayT(Number(e.target.value))}
            />
            <label className="view3d-speed">
              <span className="sr-only">Replay speed</span>
              <Select value={speed} onChange={setSpeed} options={REPLAY_SPEEDS.map((s) => ({ value: s, label: `${s}×` }))} />
            </label>
          </div>
        )}
      </section>
      <p className="view3d-credit small">Imagery © Esri, Maxar, Earthstar Geographics · Visual view of the survey</p>
    </main>
  )
}
