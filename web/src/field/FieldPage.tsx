import { useEffect, useMemo, useState } from 'react'
import { Circle, CircleMarker } from 'react-leaflet'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { DetectionDetail } from '../components/DetectionDetail'
import { formatDuration } from '../format'
import { useMissionLive } from '../live'
import { SurveyMap } from '../map/SurveyMap'
import { COLORS } from '../theme'
import {
  CATEGORY_LABELS,
  SOIL_LABELS,
  STATUS_LABELS,
  VERIFICATION_LABELS,
  type Detection,
  type LatLon,
  type Mission,
} from '../types'
import { bearing, centre, distanceM, formatDistance } from './geo'
import { useDeviceLocation, type LocationState } from './useLocation'

type Tab = 'map' | 'alerts' | 'status'

interface Ranked {
  detection: Detection
  distance: number
  direction: string
}

function NavIcon({ tab }: { tab: Tab }) {
  if (tab === 'map')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M3 6l6-2 6 2 6-2v14l-6 2-6-2-6 2z M9 4v14 M15 6v14" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
      </svg>
    )
  if (tab === 'alerts')
    return (
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path d="M12 3l10 18H2z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
        <path d="M12 10v5 M12 17.5v.5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      </svg>
    )
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="6" cy="6" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="6" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="6" cy="18" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="18" cy="18" r="3" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M8 8l8 8 M16 8l-8 8" stroke="currentColor" strokeWidth="1.8" />
    </svg>
  )
}

function DetectionRow({ item, onOpen }: { item: Ranked; onOpen: (id: number) => void }) {
  const d = item.detection
  return (
    <li>
      <button type="button" onClick={() => onOpen(d.id)}>
        <span className={`swatch swatch-${d.category}`} aria-hidden="true" />
        <span className="fd-main">
          <strong>
            #{d.id} {CATEGORY_LABELS[d.category]}
          </strong>
          <span className={`fd-status ver-${d.status}`}>{VERIFICATION_LABELS[d.status]}</span>
        </span>
        <span className="fd-dist num">
          {formatDistance(item.distance)} <small>{item.direction}</small>
        </span>
      </button>
    </li>
  )
}

function locationNote(location: LocationState): string {
  if (location.status === 'ok') return `Distances from your location (±${Math.round(location.accuracyM)} m).`
  if (location.status === 'pending') return 'Finding your location. Distances are from the centre of the survey area for now.'
  return `${location.reason}. Distances are from the centre of the survey area.`
}

function FieldMission({ missionId, missions }: { missionId: number; missions: Mission[] }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { state, replaceDetection, reconnect } = useMissionLive(missionId)
  const location = useDeviceLocation()
  const [tab, setTab] = useState<Tab>('map')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [toast, setToast] = useState<Detection | null>(null)

  const latestAlert = state.alerts[0]
  useEffect(() => {
    if (!latestAlert) return
    setToast(latestAlert.detection)
    const t = window.setTimeout(() => setToast(null), 7000)
    return () => window.clearTimeout(t)
  }, [latestAlert])

  const mission = state.mission
  const reported = useMemo(
    () => Object.values(state.detections).filter((d) => d.method === 'adaptive' && d.category !== 'clutter'),
    [state.detections],
  )
  const origin: LatLon | null =
    location.status === 'ok' ? location.position : mission ? centre(mission.area) : null
  const [originLat, originLon] = origin ?? [null, null]
  const ranked = useMemo<Ranked[]>(() => {
    if (originLat === null || originLon === null) return []
    const from: LatLon = [originLat, originLon]
    return reported
      .map((d) => ({ detection: d, distance: distanceM(from, [d.lat, d.lon]), direction: bearing(from, [d.lat, d.lon]) }))
      .sort((a, b) => a.distance - b.distance)
  }, [reported, originLat, originLon])
  const highPending = reported.filter((d) => d.category === 'high' && d.status === 'pending')
  const highAll = reported.filter((d) => d.category === 'high').sort((a, b) => b.id - a.id)

  if (!mission) {
    return (
      <div className="field-app">
        {state.connection === 'failed' ? (
          <p className="field-loading">
            Cannot reach the mission.{' '}
            <button type="button" className="link-button" onClick={reconnect}>
              Try again
            </button>
          </p>
        ) : (
          <p className="field-loading">{state.connection === 'closed' ? 'Cannot reach the mission. Retrying.' : 'Loading mission'}</p>
        )}
      </div>
    )
  }

  const t = state.telemetry
  const selected = selectedId !== null ? state.detections[selectedId] : undefined
  const progress = Math.round(mission.progress * 100)

  return (
    <div className="field-app">
      <header className="field-top">
        {highPending.length > 0 ? (
          <button type="button" className="field-alert" onClick={() => setTab('alerts')}>
            <span className="swatch swatch-high" aria-hidden="true" />
            {highPending.length} high-priority potential {highPending.length === 1 ? 'detection' : 'detections'} awaiting
            verification
          </button>
        ) : (
          <p className="field-quiet">No high-priority potential detections awaiting verification</p>
        )}
      </header>

      <main className="field-main">
        <SurveyMap
          area={mission.area}
          path={mission.path}
          track={state.track}
          swathWidthM={mission.line_spacing_m}
          uav={mission.status === 'running' || mission.status === 'completed' ? t : null}
          detections={reported}
          selectedId={selectedId}
          onSelect={setSelectedId}
        >
          {location.status === 'ok' && (
            <>
              <Circle center={location.position} radius={location.accuracyM} interactive={false} pathOptions={{ color: COLORS.survey, weight: 1, fillOpacity: 0.08 }} />
              <CircleMarker center={location.position} radius={7} interactive={false} pathOptions={{ color: '#ffffff', weight: 2.5, fillColor: COLORS.survey, fillOpacity: 1 }} />
            </>
          )}
        </SurveyMap>

        {tab === 'map' && (
          <section className="drone-card" aria-label="UAV status">
            <div className="drone-card-head">
              <span className={`status status-${mission.status}`}>{STATUS_LABELS[mission.status]}</span>
              <span className="num">{progress}% of path</span>
            </div>
            <div className="progress dark" aria-hidden="true">
              <div style={{ width: `${progress}%` }} />
            </div>
            <dl>
              <div>
                <dt>Battery</dt>
                <dd className={`num${t && t.battery_pct < 25 ? ' warn' : ''}`}>{t ? `${t.battery_pct}%` : '–'}</dd>
              </div>
              <div>
                <dt>Height</dt>
                <dd className="num">{t ? `${t.relative_alt_m.toFixed(1)} m` : '–'}</dd>
              </div>
              <div>
                <dt>Nearest</dt>
                <dd className="num">{ranked[0] ? `${formatDistance(ranked[0].distance)} ${ranked[0].direction}` : '–'}</dd>
              </div>
            </dl>
          </section>
        )}

        {tab === 'alerts' && (
          <section className="field-panel" aria-labelledby="alerts-title">
            <h1 id="alerts-title">High priority</h1>
            {highAll.length === 0 ? (
              <p className="small">No high-priority potential detections in this mission.</p>
            ) : (
              <ul className="fd-list">
                {ranked
                  .filter((r) => r.detection.category === 'high')
                  .map((r) => (
                    <DetectionRow key={r.detection.id} item={r} onOpen={setSelectedId} />
                  ))}
              </ul>
            )}
            <h2>Nearest potential detections</h2>
            <p className="small">{locationNote(location)}</p>
            {ranked.length === 0 ? (
              <p className="small">Nothing reported yet.</p>
            ) : (
              <ul className="fd-list">
                {ranked.map((r) => (
                  <DetectionRow key={r.detection.id} item={r} onOpen={setSelectedId} />
                ))}
              </ul>
            )}
          </section>
        )}

        {tab === 'status' && (
          <section className="field-panel" aria-labelledby="status-title">
            <h1 id="status-title">{mission.name}</h1>
            <p className="small">
              {SOIL_LABELS[mission.soil_type]}, sensor height {mission.altitude_m} m, lanes every {mission.line_spacing_m} m
            </p>
            <div className="row spread">
              <span className={`status status-${mission.status}`}>{STATUS_LABELS[mission.status]}</span>
              <span className="num">{progress}% of path</span>
            </div>
            <dl className="telemetry">
              <div>
                <dt>Battery</dt>
                <dd className="num">{t ? `${t.battery_pct}%` : '–'}</dd>
              </div>
              <div>
                <dt>Height</dt>
                <dd className="num">{t ? `${t.relative_alt_m.toFixed(2)} m` : '–'}</dd>
              </div>
              <div>
                <dt>Speed</dt>
                <dd className="num">{t ? `${t.ground_speed_mps.toFixed(1)} m/s` : '–'}</dd>
              </div>
              <div>
                <dt>Heading</dt>
                <dd className="num">{t ? `${Math.round(t.heading_deg)}°` : '–'}</dd>
              </div>
              <div>
                <dt>Flight time</dt>
                <dd className="num">{formatDuration(t?.t_s ?? 0)}</dd>
              </div>
              <div>
                <dt>Live link</dt>
                <dd>
                  {state.connection === 'open' ? (
                    'Connected'
                  ) : state.connection === 'failed' ? (
                    <button type="button" className="link-button" onClick={reconnect}>
                      Lost, try again
                    </button>
                  ) : (
                    'Reconnecting'
                  )}
                </dd>
              </div>
            </dl>
            <p className="small">{locationNote(location)}</p>

            <label className="field">
              <span>Mission</span>
              <select value={missionId} onChange={(e) => navigate(`/field/${e.target.value}`)}>
                {missions.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({STATUS_LABELS[m.status]})
                  </option>
                ))}
              </select>
            </label>
            <div className="row spread">
              <span className="small">Signed in as {user?.full_name}</span>
              <button type="button" className="button secondary" onClick={logout}>
                Sign out
              </button>
            </div>
            <p className="footnote">Simulated survey data. Every marker is a potential detection until trained personnel verify it.</p>
          </section>
        )}

        {toast && (
          <button
            type="button"
            className="toast field-toast"
            onClick={() => {
              setSelectedId(toast.id)
              setToast(null)
            }}
          >
            <span className="swatch swatch-high" aria-hidden="true" />
            <span>
              <strong>New high-priority potential detection</strong>
              <span className="small">Detection #{toast.id}. Tap to review.</span>
            </span>
          </button>
        )}
      </main>

      <nav className="field-nav" aria-label="Field views">
        {(['map', 'alerts', 'status'] as Tab[]).map((key) => (
          <button
            key={key}
            type="button"
            aria-current={tab === key ? 'page' : undefined}
            onClick={() => {
              setTab(key)
              setSelectedId(null)
            }}
          >
            <NavIcon tab={key} />
            <span>{key === 'map' ? 'Map' : key === 'alerts' ? 'Alerts' : 'Status'}</span>
            {key === 'alerts' && highPending.length > 0 && <i className="badge num">{highPending.length}</i>}
          </button>
        ))}
      </nav>

      {selected && (
        <div className="field-sheet" role="dialog" aria-modal="true" aria-label={`Detection ${selected.id}`}>
          <DetectionDetail detection={selected} onClose={() => setSelectedId(null)} onUpdated={replaceDetection} />
        </div>
      )}
    </div>
  )
}

/** Mobile-first view for field personnel: map, alerts, nearest detections and verification. */
export function FieldPage() {
  const params = useParams()
  const [missions, setMissions] = useState<Mission[] | null>(null)
  const { logout } = useAuth()

  useEffect(() => {
    api<Mission[]>('/api/missions')
      .then(setMissions)
      .catch(() => setMissions([]))
  }, [params.id])

  const requested = params.id ? Number(params.id) : null
  // Default: a mission that is flying now, otherwise the most recent one.
  const fallback = missions?.find((m) => m.status === 'running') ?? missions?.[0]
  const missionId = requested ?? fallback?.id ?? null

  if (missionId === null) {
    return (
      <div className="field-app">
        <div className="field-empty">
          {missions === null ? (
            <p>Loading missions</p>
          ) : (
            <>
              <h1>No missions yet</h1>
              <p>Missions appear here once the supervisor plans them.</p>
              <button type="button" className="button secondary" onClick={logout}>
                Sign out
              </button>
            </>
          )}
        </div>
      </div>
    )
  }
  return <FieldMission key={missionId} missionId={missionId} missions={missions ?? []} />
}
