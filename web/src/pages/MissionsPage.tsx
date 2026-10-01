import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { areaSize, formatDate } from '../format'
import { SOIL_LABELS, STATUS_LABELS, type Mission } from '../types'

export function MissionsPage() {
  const { user } = useAuth()
  const [missions, setMissions] = useState<Mission[] | null>(null)
  const [error, setError] = useState<string | null>(null)

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
          <Link to="/missions/new" className="button">
            New mission
          </Link>
        )}
      </div>
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
    </main>
  )
}
