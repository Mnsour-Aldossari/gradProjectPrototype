import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { formatDate, formatDuration } from '../format'
import { CATEGORY_LABELS, SOIL_LABELS, STATUS_LABELS, type Category, type MissionHistory } from '../types'

const CATEGORIES: Category[] = ['high', 'suspect', 'clutter']

export function HistoryPage() {
  const [history, setHistory] = useState<MissionHistory | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api<MissionHistory>('/api/missions/history')
      .then(setHistory)
      .catch((e) => setError(e instanceof Error ? e.message : 'Could not load the mission history'))
  }, [])

  const v = history?.totals_verification
  const reportedTotal = v ? v.pending + v.confirmed_by_team + v.false_alarm : 0

  return (
    <main className="page history">
      <h1>Mission history</h1>
      {error && <p className="error">{error}</p>}
      {!history && !error && <p className="small">Loading mission history</p>}

      {history && history.missions.length === 0 && (
        <p className="empty">No finished missions yet. Missions appear here once a survey has completed.</p>
      )}

      {history && history.missions.length > 0 && (
        <>
          <section className="stat-row" aria-label="Totals over finished missions">
            <div className="stat">
              <span className="num">{history.completed}</span>
              <span>Completed missions{history.failed > 0 ? `, ${history.failed} failed` : ''}</span>
            </div>
            {CATEGORIES.map((c) => (
              <div key={c} className={`stat stat-${c}`}>
                <span className="num">{history.totals_adaptive[c]}</span>
                <span>
                  <i className={`swatch swatch-${c}`} aria-hidden="true" /> {CATEGORY_LABELS[c]}
                </span>
              </div>
            ))}
            <div className="stat">
              <span className="num">
                {reportedTotal - (v?.pending ?? 0)} of {reportedTotal}
              </span>
              <span>Reported potential detections verified</span>
            </div>
          </section>
          <p className="small">
            Counts are potential detections from the adaptive classifier. Verified means field personnel recorded
            "confirmed by team" ({v?.confirmed_by_team ?? 0}) or "false alarm" ({v?.false_alarm ?? 0}).
          </p>

          <div className="table-scroll">
            <table className="table num-table history-table">
              <thead>
                <tr>
                  <th>Mission</th>
                  <th>Finished</th>
                  <th>Soil</th>
                  <th>Flight time</th>
                  <th title="High priority">High</th>
                  <th title="Needs verification">Verify</th>
                  <th title="Likely clutter">Clutter</th>
                  <th>Verified</th>
                  <th title="High-priority alarms from the fixed-threshold baseline, for comparison">Baseline</th>
                </tr>
              </thead>
              <tbody>
                {history.missions.map(({ mission: m, adaptive, verification, baseline_high }) => {
                  const reported = verification.pending + verification.confirmed_by_team + verification.false_alarm
                  return (
                    <tr key={m.id}>
                      <th>
                        <Link to={`/missions/${m.id}`}>{m.name}</Link>
                        {m.status === 'failed' && <span className="status status-failed">{STATUS_LABELS.failed}</span>}
                      </th>
                      <td>{formatDate(m.completed_at)}</td>
                      <td>{SOIL_LABELS[m.soil_type]}</td>
                      <td className="num">{formatDuration(m.estimated_duration_s)}</td>
                      <td className="num">{adaptive.high}</td>
                      <td className="num">{adaptive.suspect}</td>
                      <td className="num">{adaptive.clutter}</td>
                      <td className="num">
                        {reported - verification.pending} of {reported}
                      </td>
                      <td className="num">{baseline_high}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <p className="small">
            Flight time is the simulated survey duration, not the playback time. The baseline column counts high-priority
            alarms from the fixed metal-detector threshold, kept for comparison.
          </p>
        </>
      )}
    </main>
  )
}
