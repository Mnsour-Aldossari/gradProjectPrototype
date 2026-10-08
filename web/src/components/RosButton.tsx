import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

/** GET /api/ros: whether this backend can start ROS 2 (Windows with WSL) and whether it runs. */
export interface RosStatus {
  available: boolean
  running: boolean
  distro: string
  message: string
}

const ICON = 'M5 5a2 2 0 1 0 0 .01 M19 5a2 2 0 1 0 0 .01 M12 19a2 2 0 1 0 0 .01 M6.5 6.5l4.3 10.6 M17.5 6.5l-4.3 10.6 M7 5h10'
const POLL_MS = 15_000

/**
 * The supervisor's ROS 2 switch in the menu: starts or stops the project's ROS 2 nodes in WSL (the mission bridge,
 * the detector node and mission control, and PX4's link where it is built), so nobody types commands in a terminal.
 * Hidden where the backend cannot start them (not Windows with WSL).
 */
export function RosButton({ folded }: { folded: boolean }) {
  const [status, setStatus] = useState<RosStatus | null>(null)
  const [busy, setBusy] = useState<'start' | 'stop' | null>(null)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api<RosStatus>('/api/ros')
      .then(setStatus)
      .catch(() => setStatus(null))
  }, [])

  useEffect(() => {
    load()
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') load()
    }, POLL_MS)
    return () => window.clearInterval(timer)
  }, [load])

  if (!status?.available) return null

  const action = status.running ? 'stop' : 'start'
  const state = busy === 'start' ? 'Starting…' : busy === 'stop' ? 'Stopping…' : status.running ? 'On' : 'Off'
  const label = `ROS 2: ${state}`
  const tip = status.running
    ? `ROS 2 runs in WSL (${status.distro}): it follows every mission and takes ROS commands. Click to stop it.`
    : `Start ROS 2 in WSL (${status.distro}): it follows every mission and takes ROS commands.`

  async function toggle() {
    setBusy(action)
    setError('')
    try {
      setStatus(await api<RosStatus>(`/api/ros/${action}`, { method: 'POST' }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      load()
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="ros">
      <button
        type="button"
        className={`side-fold ros-button${status.running ? ' is-on' : ''}`}
        title={folded ? `${label}. ${tip}` : tip}
        aria-pressed={status.running}
        disabled={busy !== null}
        onClick={toggle}
      >
        <span className="ros-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d={ICON} />
          </svg>
          <span className="ros-dot" aria-hidden="true" />
        </span>
        <span className="ros-label">
          ROS 2 <span className="ros-state">{state}</span>
        </span>
      </button>
      <p className="ros-error" role="status" aria-live="polite">
        {error}
      </p>
    </div>
  )
}
