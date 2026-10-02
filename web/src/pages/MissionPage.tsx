import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { DetectionDetail } from '../components/DetectionDetail'
import { SensorTrace } from '../components/SensorTrace'
import { formatDuration } from '../format'
import { useMissionLive } from '../live'
import { SurveyMap } from '../map/SurveyMap'
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

  return (
    <main className="mission-page">
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
        </div>
      </header>

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

      <div className="mp-grid">
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
              <section className="card card-pad block" aria-labelledby="flight-heading">
                <div className="card-head">
                  <h2 id="flight-heading">Flight</h2>
                  <span className="small">{linkLabel}</span>
                </div>
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
              </section>

              {mission.status === 'running' && (
                <section className="card card-pad block" aria-labelledby="sensors-heading">
                  <h2 id="sensors-heading">Sensors</h2>
                  <SensorTrace md={state.trace.md} gpr={state.trace.gpr} />
                </section>
              )}

              <section className="card card-pad block" aria-labelledby="det-heading">
                <div className="card-head">
                  <h2 id="det-heading">Potential detections</h2>
                  <span className="small">{reported.length} to verify</span>
                </div>
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
              </section>

              {profile && (
                <section className="card card-pad block" aria-labelledby="profile-heading">
                  <h2 id="profile-heading">How the classifier adapts here</h2>
                  <ul className="notes">
                    {profile.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                </section>
              )}

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
