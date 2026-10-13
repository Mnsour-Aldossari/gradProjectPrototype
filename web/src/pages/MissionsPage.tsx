import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { areaSize, formatDate } from '../format'
import { SOIL_LABELS, STATUS_LABELS, type Mission, type MissionPage } from '../types'

const PAGE_SIZE = 10
const SEARCH_DELAY_MS = 300

export function MissionsPage() {
  const { user } = useAuth()
  const [result, setResult] = useState<MissionPage | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [startingDemo, setStartingDemo] = useState(false)
  const navigate = useNavigate()

  // Filters and page live in the address, so the back button returns to the same list.
  const [params, setParams] = useSearchParams()
  const q = params.get('q') ?? ''
  const status = params.get('status') ?? ''
  const soil = params.get('soil') ?? ''
  const page = Math.max(1, Number(params.get('page')) || 1)
  const [text, setText] = useState(q)
  const filtered = q !== '' || status !== '' || soil !== ''

  function update(changes: Record<string, string>) {
    // Read from the address bar, not this render's params, so a delayed search never undoes a newer filter.
    const next = new URLSearchParams(window.location.search)
    for (const [key, value] of Object.entries(changes)) {
      if (value === '' || (key === 'page' && value === '1')) next.delete(key)
      else next.set(key, value)
    }
    setParams(next, { replace: true })
  }

  useEffect(() => {
    if (text.trim() === q) return
    const timer = setTimeout(() => update({ q: text.trim(), page: '1' }), SEARCH_DELAY_MS)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [text])

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
    let current = true
    const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) })
    if (q) query.set('q', q)
    if (status) query.set('status', status)
    if (soil) query.set('soil_type', soil)
    setError(null)
    api<MissionPage>(`/api/missions/search?${query}`)
      .then((r) => {
        if (!current) return
        const last = Math.max(1, Math.ceil(r.total / r.page_size))
        if (page > last) update({ page: String(last) })
        else setResult(r)
      })
      .catch((e) => current && setError(e instanceof Error ? e.message : 'Could not load missions'))
    return () => {
      current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, status, soil, page])

  const missions: Mission[] | null = result?.items ?? null
  const total = result?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const first = (page - 1) * PAGE_SIZE + 1

  return (
    <main className="page">
      <div className="page-head">
        <h1>Missions</h1>
        {user?.role === 'supervisor' && (
          <div className="row">
            <button type="button" className="button secondary" onClick={runDemo} disabled={startingDemo}>
              {startingDemo ? 'Starting demo' : 'Run demo scenario'}
            </button>
            <Link to="/missions/new" className="button">
              New mission
            </Link>
          </div>
        )}
      </div>
      {user?.role === 'supervisor' && (
        <p className="small demo-note">
          The demo scenario is fixed: evaluation seed 2000, dry sand, the standard 60 × 40 m test field, played at
          20× speed. It produces the same potential detections every time it runs.
        </p>
      )}
      <div className="filters" role="search">
        <label className="field">
          <span>Search</span>
          <input
            type="search"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="Mission name"
            maxLength={100}
          />
        </label>
        <label className="field">
          <span>Status</span>
          <select value={status} onChange={(e) => update({ status: e.target.value, page: '1' })}>
            <option value="">All statuses</option>
            {Object.entries(STATUS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Soil</span>
          <select value={soil} onChange={(e) => update({ soil: e.target.value, page: '1' })}>
            <option value="">All soils</option>
            {Object.entries(SOIL_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        {filtered && (
          <button
            type="button"
            className="button secondary"
            onClick={() => {
              setText('')
              setParams(new URLSearchParams(), { replace: true })
            }}
          >
            Clear filters
          </button>
        )}
      </div>
      {error && <p className="error">{error}</p>}
      {missions === null && !error && <p className="small">Loading missions</p>}
      {missions?.length === 0 && filtered && <p className="empty">No missions match these filters.</p>}
      {missions?.length === 0 && !filtered && (
        <p className="empty">
          {user?.role === 'supervisor'
            ? 'No missions yet. Create one to plan the first survey.'
            : 'No missions yet. Missions appear here once the supervisor plans them.'}
        </p>
      )}
      {missions && missions.length > 0 && (
        <table className="table">
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
                    <Link to={`/missions/${m.id}`}>{m.name}</Link>
                  </td>
                  <td>{SOIL_LABELS[m.soil_type]}</td>
                  <td className="num">
                    {size.width.toFixed(0)} × {size.height.toFixed(0)} m
                  </td>
                  <td>
                    <span className={`status status-${m.status}`}>{STATUS_LABELS[m.status]}</span>
                  </td>
                  <td>{formatDate(m.created_at)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
      {missions && total > 0 && (
        <nav className="pager" aria-label="Pages">
          <span className="small">
            {first}–{first + missions.length - 1} of {total}
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
    </main>
  )
}
