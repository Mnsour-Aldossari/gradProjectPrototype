import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { areaSize, formatDate } from '../format'
import { SOIL_LABELS, STATUS_LABELS, type Mission } from '../types'

/** The survey outline, drawn small next to the mission's name. */
function AreaThumb({ area }: { area: Mission['area'] }) {
  if (area.length < 3) return <span className="mthumb" aria-hidden="true" />
  const lats = area.map((p) => p[0])
  const lons = area.map((p) => p[1])
  const [minLat, maxLat, minLon, maxLon] = [Math.min(...lats), Math.max(...lats), Math.min(...lons), Math.max(...lons)]
  const span = Math.max(maxLat - minLat, (maxLon - minLon) * Math.cos((minLat * Math.PI) / 180), 1e-9)
  const pts = area
    .map(([lat, lon]) => {
      const x = 6 + (((lon - minLon) * Math.cos((minLat * Math.PI) / 180)) / span) * 28
      const y = 34 - ((lat - minLat) / span) * 28
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <span className="mthumb" aria-hidden="true">
      <svg viewBox="0 0 40 40">
        <polygon points={pts} />
      </svg>
    </span>
  )
}

const STAT_ICONS = {
  all: 'M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z M9 3v15 M15 6v15',
  flying: 'M12 2v4 M12 18v4 M2 12h4 M18 12h4 M12 8a4 4 0 1 0 0 8a4 4 0 1 0 0-8',
  done: 'M20 6 9 17l-5-5',
  area: 'M3 3h18v18H3z M3 9h18 M3 15h18 M9 3v18 M15 3v18',
}

function Stat({ tone, icon, value, label }: { tone: string; icon: string; value: string; label: string }) {
  return (
    <div className={`mstat mstat-${tone}`}>
      <span className="mstat-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d={icon} />
        </svg>
      </span>
      <b className="mstat-value">{value}</b>
      <span className="mstat-label">{label}</span>
    </div>
  )
}

export function MissionsPage() {
  const { user } = useAuth()
  const [missions, setMissions] = useState<Mission[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [startingDemo, setStartingDemo] = useState(false)
  const navigate = useNavigate()
  const supervisor = user?.role === 'supervisor'

  async function runDemo() {
    setStartingDemo(true)
    setError(null)
    try {
      const mission = await api<Mission>('/api/missions/demo', { method: 'POST' })
      navigate(`/missions/${mission.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start the demo scenario')
      setStartingDemo(false)
    }
  }

  useEffect(() => {
    api<Mission[]>('/api/missions')
      .then(setMissions)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load missions'))
  }, [])

  const list = missions ?? []
  const flying = list.filter((m) => m.status === 'running').length
  const done = list.filter((m) => m.status === 'completed').length
  const hectares = list.reduce((sum, m) => {
    const s = areaSize(m.area)
    return sum + (s.width * s.height) / 10_000
  }, 0)

  return (
    <main className="page page-wide">
      <header className="hero">
        <div className="hero-text">
          <p className="eyebrow">
            <span className="pulse-dot" aria-hidden="true" /> Mission control
          </p>
          <h1>Missions</h1>
          <p className="hero-lede">
            Plan a survey, watch the UAV sweep the field live, and review every potential detection in one place.
          </p>
        </div>
        {supervisor && (
          <div className="row hero-actions">
            <button type="button" className="button secondary" onClick={runDemo} disabled={startingDemo}>
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M7 4.5v15l12-7.5z" fill="currentColor" />
              </svg>
              {startingDemo ? 'Starting demo' : 'Run demo scenario'}
            </button>
            <Link to="/missions/new" className="button">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
                <path d="M12 5v14 M5 12h14" />
              </svg>
              New mission
            </Link>
          </div>
        )}
      </header>

      {missions && missions.length > 0 && (
        <section className="mstats" aria-label="Missions at a glance">
          <Stat tone="brand" icon={STAT_ICONS.all} value={String(list.length)} label="Missions" />
          <Stat tone="sky" icon={STAT_ICONS.flying} value={String(flying)} label="In flight now" />
          <Stat tone="ok" icon={STAT_ICONS.done} value={String(done)} label="Completed" />
          <Stat tone="amber" icon={STAT_ICONS.area} value={`${hectares.toFixed(2)} ha`} label="Area planned" />
        </section>
      )}

      {supervisor && (
        <aside className="demo-card">
          <span className="demo-card-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M7 4.5v15l12-7.5z" fill="currentColor" />
            </svg>
          </span>
          <p className="small demo-note">
            <b>Demo scenario.</b> The demo scenario is fixed: evaluation seed 2000, dry sand, the standard 60 × 40 m test
            field, played at 20× speed. It produces the same potential detections every time it runs.
          </p>
        </aside>
      )}

      {error && <p className="error">{error}</p>}
      {missions === null && !error && <p className="small">Loading missions</p>}
      {missions?.length === 0 && (
        <div className="empty empty-hero">
          <span className="empty-art" aria-hidden="true" />
          <p>
            {supervisor
              ? 'No missions yet. Create one to plan the first survey.'
              : 'No missions yet. Missions appear here once the supervisor plans them.'}
          </p>
        </div>
      )}
      {missions && missions.length > 0 && (
        <section className="card table-card">
          <div className="table-card-head">
            <h2>All missions</h2>
            <span className="count-chip">{missions.length}</span>
          </div>
          <table className="table missions-table">
            <thead>
              <tr>
                <th>Mission</th>
                <th>Soil</th>
                <th>Area</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {missions.map((m) => {
                const size = areaSize(m.area)
                return (
                  <tr key={m.id}>
                    <td>
                      <span className="mname">
                        <AreaThumb area={m.area} />
                        <Link to={`/missions/${m.id}`}>{m.name}</Link>
                      </span>
                    </td>
                    <td>
                      <span className={`soil soil-${m.soil_type}`}>{SOIL_LABELS[m.soil_type]}</span>
                    </td>
                    <td className="num">
                      {size.width.toFixed(0)} × {size.height.toFixed(0)} m
                    </td>
                    <td>
                      <span className={`status status-${m.status}`}>{STATUS_LABELS[m.status]}</span>
                    </td>
                    <td className="when">{formatDate(m.created_at)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </section>
      )}
    </main>
  )
}
