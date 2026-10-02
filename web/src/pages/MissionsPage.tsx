import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { areaSize, formatDate } from '../format'
import { SOIL_LABELS, STATUS_LABELS, type Mission } from '../types'

export function MissionsPage() {
  const { user } = useAuth()
  const [missions, setMissions] = useState<Mission[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [startingDemo, setStartingDemo] = useState(false)
  const navigate = useNavigate()

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
      {error && <p className="error">{error}</p>}
      {missions === null && !error && <p className="small">Loading missions</p>}
      {missions?.length === 0 && (
        <p className="empty">
          {user?.role === 'supervisor'
            ? 'No missions yet. Create one to plan the first survey.'
            : 'No missions yet. Missions appear here once the supervisor plans them.'}
        </p>
      )}
      {missions && missions.length > 0 && (
        <table className="table clickable-rows">
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
    </main>
  )
}
