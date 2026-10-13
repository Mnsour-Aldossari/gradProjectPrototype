import { useEffect, useId, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { areaSize, formatDate } from '../format'
import { allPoints, PastKey, PastMissions } from '../map/PastMissions'
import { Select } from '../components/Select'
import { SurveyMap } from '../map/SurveyMap'
import { SOIL_LABELS, STATUS_LABELS, type Mission, type MissionStatus, type SoilType } from '../types'

const PAGE_SIZE = 12

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  ...(Object.entries(STATUS_LABELS) as [MissionStatus, string][]).map(([value, label]) => ({ value, label })),
]
const SOIL_OPTIONS = [
  { value: '', label: 'All soils' },
  ...(Object.entries(SOIL_LABELS) as [SoilType, string][]).map(([value, label]) => ({ value, label })),
]

/** The survey outline, drawn small next to the mission's name. */
function AreaThumb({ area }: { area: Mission['area'] }) {
  const lanes = useId().replace(/:/g, '')
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
        <defs>
          <pattern id={lanes} width="40" height="2.2" patternUnits="userSpaceOnUse">
            <line x1="0" y1="1.1" x2="40" y2="1.1" />
          </pattern>
        </defs>
        <polygon points={pts} />
        <polygon points={pts} className="mthumb-lanes" style={{ fill: `url(#${lanes})` }} />
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

  // Search, filters and page live in the address, so the back button returns to the same list.
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const statusFilter = params.get('status') ?? ''
  const soilFilter = params.get('soil') ?? ''
  const filtered = q.trim() !== '' || statusFilter !== '' || soilFilter !== ''

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === '' || (key === 'page' && value === '1')) next.delete(key)
      else next.set(key, value)
    }
    setParams(next, { replace: true })
  }

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
  const needle = q.trim().toLowerCase()
  const matches = list.filter(
    (m) =>
      (needle === '' || m.name.toLowerCase().includes(needle)) &&
      (statusFilter === '' || m.status === statusFilter) &&
      (soilFilter === '' || m.soil_type === soilFilter),
  )
  const pages = Math.max(1, Math.ceil(matches.length / PAGE_SIZE))
  const page = Math.min(pages, Math.max(1, Number(params.get('page')) || 1))
  const first = (page - 1) * PAGE_SIZE
  const shown = matches.slice(first, first + PAGE_SIZE)
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
      {missions && missions.some((m) => m.area.length >= 3) && (
        <section className="overview" aria-labelledby="overview-title">
          <div className="section-head">
            <h2 id="overview-title">Survey map</h2>
            <span className="small">Every planned outline, in its status colour. Click one to open it.</span>
          </div>
          <div className="overview-map-wrap">
            <SurveyMap
              area={[]}
              fitTo={allPoints(missions)}
              className="overview-map"
            >
              <PastMissions missions={missions.filter((m) => m.area.length >= 3)} onSelect={(m) => navigate(`/missions/${m.id}`)} />
            </SurveyMap>
          </div>
          <PastKey />
        </section>
      )}

      {missions && missions.length > 0 && (
        <section className="mgrid-wrap" aria-labelledby="all-missions">
          <div className="section-head">
            <h2 id="all-missions">All missions</h2>
            <span className="count-chip">{filtered ? `${matches.length} of ${missions.length}` : missions.length}</span>
          </div>
          <div className="mfilters" role="search">
            <label className="field">
              <span>Search</span>
              <input
                type="search"
                value={q}
                onChange={(e) => update({ q: e.target.value, page: '1' })}
                placeholder="Mission name"
                maxLength={100}
              />
            </label>
            <label className="field">
              <span>Status</span>
              <Select value={statusFilter} options={STATUS_OPTIONS} onChange={(v) => update({ status: v, page: '1' })} />
            </label>
            <label className="field">
              <span>Soil</span>
              <Select value={soilFilter} options={SOIL_OPTIONS} onChange={(v) => update({ soil: v, page: '1' })} />
            </label>
            {filtered && (
              <button type="button" className="button secondary" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                Clear filters
              </button>
            )}
          </div>
          {matches.length === 0 && <p className="empty">No missions match these filters.</p>}
          <ul className="mgrid">
            {shown.map((m) => {
              const size = areaSize(m.area)
              return (
                <li key={m.id} className={`mcard mcard-${m.status}`}>
                  <div className="mcard-map">
                    <AreaThumb area={m.area} />
                    <span className={`status status-${m.status}`}>{STATUS_LABELS[m.status]}</span>
                    {m.status === 'running' && (
                      <span className="mcard-progress" aria-hidden="true">
                        <span style={{ width: `${Math.round(m.progress * 100)}%` }} />
                      </span>
                    )}
                  </div>
                  <div className="mcard-body">
                    <h3>
                      <Link to={`/missions/${m.id}`}>{m.name}</Link>
                    </h3>
                    <dl className="mcard-facts">
                      <div>
                        <dt>Soil</dt>
                        <dd>
                          <span className={`soil soil-${m.soil_type}`}>{SOIL_LABELS[m.soil_type]}</span>
                        </dd>
                      </div>
                      <div>
                        <dt>Area</dt>
                        <dd className="num">
                          {size.width.toFixed(0)} × {size.height.toFixed(0)} m
                        </dd>
                      </div>
                    </dl>
                    <p className="mcard-when">{formatDate(m.created_at)}</p>
                  </div>
                </li>
              )
            })}
            {supervisor && !filtered && page === pages && (
              <li className="mcard mcard-add">
                <Link to="/missions/new" className="mcard-add-link">
                  <span className="mcard-add-icon" aria-hidden="true">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                      <path d="M12 5v14 M5 12h14" />
                    </svg>
                  </span>
                  Plan another survey
                </Link>
              </li>
            )}
          </ul>
          {matches.length > PAGE_SIZE && (
            <nav className="pager" aria-label="Pages of missions">
              <span className="small">
                {first + 1}–{first + shown.length} of {matches.length}
              </span>
              <div className="row">
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => update({ page: String(page - 1) })}
                  disabled={page <= 1}
                >
                  Previous
                </button>
                <span className="small">
                  Page {page} of {pages}
                </span>
                <button
                  type="button"
                  className="button secondary"
                  onClick={() => update({ page: String(page + 1) })}
                  disabled={page >= pages}
                >
                  Next
                </button>
              </div>
            </nav>
          )}
        </section>
      )}
    </main>
  )
}
