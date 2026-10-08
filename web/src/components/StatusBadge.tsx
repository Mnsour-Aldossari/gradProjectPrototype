import { PHASE_LABELS, STATUS_LABELS, type Mission } from '../types'

/**
 * The mission's status, or while it flies what the UAV is doing after a supervisor's command (paused, returning).
 * `label` ("Flight") names it where the sensor collection is shown next to it (SensorBadge).
 */
export function StatusBadge({ mission, label }: { mission: Mission; label?: string }) {
  const phase = mission.status === 'running' && mission.phase && mission.phase !== 'surveying' ? mission.phase : null
  const text = phase ? PHASE_LABELS[phase] : STATUS_LABELS[mission.status]
  return (
    <span className={`status status-${phase ?? mission.status}`}>
      {label ? `${label}: ${text}` : text}
    </span>
  )
}
