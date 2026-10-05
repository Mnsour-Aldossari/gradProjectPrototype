import { useEffect, useMemo, useState } from 'react'
import { Circle, CircleMarker, Tooltip } from 'react-leaflet'
import { useNavigate, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { DetectionDetail } from '../components/DetectionDetail'
import { DisplayMenu } from '../components/DisplayMenu'
import { formatDuration } from '../format'
import { useMissionLive } from '../live'
import { SurveyMap, type FitPadding } from '../map/SurveyMap'
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
import { FieldMapInfo } from './FieldMapInfo'
import { bearing, centre, distanceM, FAR_FROM_AREA_M, formatDistance, testPosition } from './geo'
import type { Ranked } from './mapInfo'
import { useDeviceLocation } from './useLocation'

type Tab = 'map' | 'alerts' | 'status'

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

/** Where distances are measured from, and why. */
type LocationInfo =
  | { kind: 'real'; accuracyM: number }
  | { kind: 'test'; why: string }
  | { kind: 'centre'; why: string }

function LocationNote({ info, canUseReal, canUseTest, onChoose }: {
  info: LocationInfo
  canUseReal: boolean
  canUseTest: boolean
  onChoose: (choice: 'test' | 'real') => void
}) {
  return (
    <div className="location-note">
      <p className="small">
        {info.kind === 'test' && <span className="test-badge">Test location</span>}{' '}
        {info.kind === 'real' && `Distances from your location (±${Math.round(info.accuracyM)} m).`}
        {info.kind === 'test' &&
          `Distances are measured from a fixed point inside the survey area, not from your real position. ${info.why}`}
        {info.kind === 'centre' && info.why}
      </p>
      {info.kind === 'test' && canUseReal && (
        <button type="button" className="link-button" onClick={() => onChoose('real')}>
          Use my real location
        </button>
      )}
      {info.kind === 'real' && canUseTest && (
        <button type="button" className="link-button" onClick={() => onChoose('test')}>
          Use test location
        </button>
      )}
    </div>
  )
}

function FieldMission({ missionId, missions }: { missionId: number; missions: Mission[] }) {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const { state, replaceDetection, reconnect } = useMissionLive(missionId)
  const device = useDeviceLocation()
  const [choice, setChoice] = useState<'test' | 'real' | null>(null)
  const [tab, setTab] = useState<Tab>('map')
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [toast, setToast] = useState<Detection | null>(null)
  // What the cards over the map cover, so the survey area is fitted into the free part.
  const [insets, setInsets] = useState<FitPadding | undefined>(undefined)

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
  // Test location: a fixed point inside the survey area. It is the default when the real position cannot be
  // used (permission refused, no GPS, or the device is far from the area), and can be switched by the user.
  const testPos = mission ? testPosition(mission.area) : null
  const farM = device.status === 'ok' && mission ? distanceM(device.position, centre(mission.area)) : 0
  const deviceFar = farM > FAR_FROM_AREA_M
  const useTest = testPos !== null && (choice ? choice === 'test' : device.status === 'unavailable' || deviceFar)
  const info: LocationInfo = useTest
    ? {
        kind: 'test',
        why:
          choice === 'test'
            ? 'You chose the test location.'
            : device.status === 'unavailable'
              ? `${device.reason}.`
              : `Your real location is ${formatDistance(farM)} from the survey area.`,
      }
    : device.status === 'ok'
      ? { kind: 'real', accuracyM: device.accuracyM }
      : { kind: 'centre', why: 'Finding your location. Distances are from the centre of the survey area for now.' }
  const origin: LatLon | null = useTest ? testPos : device.status === 'ok' ? device.position : mission ? centre(mission.area) : null
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
          fitPadding={insets}
        >
          {info.kind === 'real' && device.status === 'ok' && (
            <>
              <Circle center={device.position} radius={device.accuracyM} interactive={false} pathOptions={{ color: COLORS.survey, weight: 1, fillOpacity: 0.08 }} />
              <CircleMarker center={device.position} radius={7} interactive={false} pathOptions={{ color: '#ffffff', weight: 2.5, fillColor: COLORS.survey, fillOpacity: 1 }} />
            </>
          )}
          {info.kind === 'test' && testPos && (
            <CircleMarker center={testPos} radius={8} interactive={false} pathOptions={{ color: '#ffffff', weight: 2.5, fillColor: COLORS.amber, fillOpacity: 1 }}>
              <Tooltip permanent direction="top" offset={[0, -8]}>
                Test location
              </Tooltip>
            </CircleMarker>
          )}
        </SurveyMap>

        {tab === 'map' && (
          <FieldMapInfo
            mission={mission}
            telemetry={t}
            connection={state.connection}
            reported={reported}
            ranked={ranked}
            testLocation={info.kind === 'test'}
            onOpen={setSelectedId}
            onSeeAll={() => setTab('alerts')}
            onInsets={setInsets}
          />
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
            <LocationNote info={info} canUseReal={device.status === 'ok'} canUseTest={testPos !== null} onChoose={setChoice} />
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
            <LocationNote info={info} canUseReal={device.status === 'ok'} canUseTest={testPos !== null} onChoose={setChoice} />

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
            <DisplayMenu inline />
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
